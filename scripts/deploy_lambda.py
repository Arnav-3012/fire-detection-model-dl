"""Build, deploy and TEAR DOWN the Stage 6 second-opinion Lambda.

Plain zip + boto3 on purpose (developer choice, 2026-09-23): the repo
already talks to AWS through boto3 in cloud/uploader.py and
dashboard/backend/main.py, so this adds no toolchain. SAM/Terraform would
be more declarative and a new dependency to learn before a deadline; a
container image would dodge the 250MB unzipped limit we do not need to
dodge (measured: 215MB).

COST POSTURE -- the developer's stated constraint is "a few trials plus
the main demo, not a 24/7 service", and this script is built around that
rather than around a permanent deployment:

  --delete tears down the function, its URL, its role and the S3-staged
  build zip in one command.
  The cheapest Lambda is a deleted one, and forgotten infrastructure is
  what actually generates surprise bills. Run it after the demo.

  Reserved concurrency is pinned to 1. This is the AWS-side backstop for
  a runaway caller: no matter what the edge loop does, at most one
  execution runs at a time. Client-side guards (rising-edge trigger,
  cooldown, session breaker in cloud/second_opinion.py) are the first
  line; this is the one that holds when those have a bug.

  Timeout is 10s, not the 900s default. Measured warm inference is ~23ms,
  so 10s is already ~400x headroom, and it bounds what a hung invocation
  can bill.

  Memory is 512MB: enough for onnxruntime + a 640x480 decode, and the
  point on the price/speed curve where a ~1s billed invocation costs
  ~0.000008 USD. Free tier is 400,000 GB-s/month; a demo uses seconds.

A Function URL is created rather than API Gateway. It is the same
HTTPS-POST-in, JSON-out shape for this use, it is one fewer resource to
create and delete, and it has no per-million-call charge of its own.
AuthType is AWS_IAM by default so the endpoint is not world-callable --
an open URL running inference is a stranger's free GPU-less compute and
a way to run up your bill.

Usage:
    python scripts/deploy_lambda.py --build-only     # just make the zip
    python scripts/deploy_lambda.py                  # build + create/update
    python scripts/deploy_lambda.py --test           # invoke with a real frame
    python scripts/deploy_lambda.py --delete         # remove everything
"""

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Same as agent/tools.py and agent/compose.py: credentials and
# AWS_DEFAULT_REGION live in .env, and boto3 does not read it on its own.
load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "cloud" / "lambda_infer"
BUILD = ROOT / "data" / "lambda_build"
ZIP_PATH = ROOT / "data" / "firewatch_infer.zip"
MODEL_SRC = ROOT / "models" / "fire_mnv3.onnx"
# Where _upload_via_s3() stages a >50MB zip; --delete removes it too.
STAGED_ZIP_KEY = "lambda-builds/firewatch_infer.zip"

FUNCTION_NAME = "firewatch-second-opinion"
ROLE_NAME = "firewatch-second-opinion-role"
HANDLER = "handler.lambda_handler"
RUNTIME = "python3.12"
MEMORY_MB = 512
TIMEOUT_S = 10
RESERVED_CONCURRENCY = 1

# Lambda runs manylinux x86_64. This machine is arm64 macOS, so the
# wheels MUST be downloaded for the target platform -- zipping the local
# site-packages would ship Mach-O binaries that fail to import on AWS
# with an unhelpful error. --only-binary=:all: makes a missing wheel a
# loud failure here rather than a source build that silently targets the
# wrong platform.
# THE DEPENDENCY SET IS A SOLVED CONSTRAINT PROBLEM. DO NOT LOOSEN IT.
# Four constraints must hold SIMULTANEOUSLY. Each was violated once for
# real on 2026-09-23, and each cost a full build+deploy+invoke cycle to
# discover, because every one of them is invisible locally and only
# surfaces as an import error or a load error inside Lambda.
#
#   (1) IR VERSION. models/fire_mnv3.onnx is IR 10 / opset 20 (pytorch
#       2.13). onnxruntime <= 1.16.3 supports at most IR 9 and fails with
#       "Unsupported model IR version: 10". Needs ORT >= 1.17.
#
#   (2) GLIBC. Lambda's python3.11 is Amazon Linux 2 (glibc 2.26);
#       python3.12+ is AL2023 (glibc 2.34). The wheels below need 2.27,
#       so python3.11 fails with "GLIBC_2.27 not found" before the
#       handler is reached. Needs python3.12.
#
#   (3) NUMPY ABI. numpy 1.x has no python3.12 manylinux wheels, so the
#       package necessarily gets numpy 2.x. onnxruntime 1.17/1.18 were
#       compiled against numpy 1.x and abort on import with
#       "_ARRAY_API not found ... compiled using NumPy 1.x". ORT 1.18.1
#       declares numpy<2.0 explicitly; 1.19.0 dropped that cap when it
#       gained numpy 2 support. Needs ORT >= 1.19.
#
#   (4) SIZE. Lambda's hard limit is 250MB unzipped. ORT 1.29 (matching
#       the local env) is 61MB and lands the package at 277MB. opencv
#       5.0.0 is 153MB and lands it at 253MB. Both breach the limit.
#
# The solution below satisfies all four at 236MB: ORT 1.20.1 (>= 1.19 for
# numpy 2, and 37MB rather than 61MB) with opencv 4.10 (63MB rather than
# 153MB) on python3.12.
#
# OPENCV USES A DIFFERENT PLATFORM TAG ON PURPOSE. Only opencv 5.0.0
# publishes manylinux_2_28 wheels, and it is 90MB larger than 4.10 for
# no benefit here -- this code calls resize, cvtColor and imdecode only.
# A manylinux2014 wheel runs anywhere a 2_28 one does (2.14 <= 2.34), so
# mixing tags is safe in this direction and is what keeps us under 250MB.
#
# OpenCV cannot be dropped for Pillow: measured 2026-09-23, PIL's resize
# differs from cv2's on 2% of frames at the 0.30 threshold, which would
# manufacture false local/cloud disagreements. See preprocess.py.
PYTHON_VERSION = "3.12"
PLATFORM_TAG = "manylinux_2_28_x86_64"
OPENCV_PLATFORM_TAG = "manylinux2014_x86_64"

PIP_TARGET_ARGS = [
    "--platform", PLATFORM_TAG,
    "--python-version", PYTHON_VERSION,
    "--only-binary=:all:",
]

# Every version is PINNED. An unpinned dependency here silently drifts
# into one of the four failures above the next time it is built.
DEPENDENCIES = ["onnxruntime==1.20.1", "numpy"]
OPENCV_DEPENDENCY = "opencv-python-headless==4.10.0.84"

MAX_SUPPORTED_IR = 10

# Must match the arch in PIP_TARGET_ARGS' platform tag. Lambda's default
# is x86_64 today, but pinning it means the wheels and the function can
# never disagree because of a changed default.
ARCHITECTURE = "x86_64"

# Pulled in by onnxruntime for symbolic shape inference, which is a
# model-authoring path, never touched during inference. Verified on
# 2026-09-23 by blocking both modules at import and running a real
# (5,3,224,224) batch through fire_mnv3.onnx: it succeeds and neither
# module is ever imported. Removing them saves ~32MB of the 250MB budget.
PRUNE_DIRS = ["sympy", "mpmath"]
PRUNE_FILES = ["isympy.py"]


def _lambda_client():
    return boto3.client("lambda", region_name=os.environ.get("AWS_DEFAULT_REGION"))


def build_zip(verbose: bool = True) -> Path:
    """Assemble the deployment package and report its size against the limit."""
    if not MODEL_SRC.exists():
        sys.exit(f"ERROR: model not found at {MODEL_SRC}")
    _check_runtime_consistency()
    # Resolve the model's external-data requirements FIRST. A missing
    # sidecar or a missing `onnx` package is a two-second failure here,
    # versus a failure several minutes into downloading ~220MB of wheels.
    _model_files()

    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)

    print(f"Downloading linux wheels ({', '.join(DEPENDENCIES)})...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", *DEPENDENCIES,
         *PIP_TARGET_ARGS, "--target", str(BUILD), "--quiet"],
        check=True,
    )
    # Separate call so opencv can use its own (older, smaller) platform
    # tag -- see the constraint block at the top. --no-deps because numpy
    # is already installed above at the version ORT was resolved against;
    # letting opencv re-resolve it could pull a different numpy.
    print(f"Downloading {OPENCV_DEPENDENCY} ({OPENCV_PLATFORM_TAG})...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", OPENCV_DEPENDENCY, "--no-deps",
         "--platform", OPENCV_PLATFORM_TAG, "--python-version", PYTHON_VERSION,
         "--only-binary=:all:", "--target", str(BUILD), "--quiet"],
        check=True,
    )

    # Prune AFTER install so pip's dependency resolution is untouched --
    # removing them from the install list would only make pip re-add them.
    for name in PRUNE_DIRS:
        shutil.rmtree(BUILD / name, ignore_errors=True)
    for name in PRUNE_FILES:
        (BUILD / name).unlink(missing_ok=True)
    for pattern in ("**/__pycache__", "**/*.dist-info", "**/tests"):
        for path in BUILD.glob(pattern):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)

    for src in SRC.glob("*.py"):
        shutil.copy2(src, BUILD / src.name)
    _copy_model()

    _verify_build()

    unzipped_mb = sum(f.stat().st_size for f in BUILD.rglob("*") if f.is_file()) / 1e6
    ZIP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(BUILD.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(BUILD))
    zipped_mb = ZIP_PATH.stat().st_size / 1e6

    if verbose:
        print(f"\nunzipped {unzipped_mb:6.1f} MB  (AWS hard limit 250 MB)")
        print(f"zipped   {zipped_mb:6.1f} MB  (direct-upload limit 50 MB)")
    if unzipped_mb > 250:
        sys.exit("ERROR: package exceeds Lambda's 250MB unzipped limit.\n"
                 "Prune OpenCV's unused video codecs (libavcodec/libaom/libvpx,\n"
                 "~26MB in opencv_python_headless.libs) -- this workload only\n"
                 "uses resize and cvtColor. Verify the pruned build still\n"
                 "imports cv2 on Linux before relying on it.")
    if unzipped_mb > 243:
        print(f"WARNING: only {250 - unzipped_mb:.0f} MB of headroom left "
              f"under the 250MB limit.")
    if zipped_mb > 50:
        print("note: zip exceeds 50MB, so it is uploaded via S3 staging rather than directly.")
    return ZIP_PATH


def _verify_build() -> None:
    """Check the ASSEMBLED package, not just the arguments we asked for.

    _check_runtime_consistency() validates the constants agree with each
    other; this validates that what pip actually produced matches them.
    They are different questions -- a correct --python-version flag still
    yields the wrong binaries if a dependency only publishes wheels for
    another version and pip quietly picks a different one.

    Every check here corresponds to a failure that cost a real deploy
    cycle on 2026-09-23, and each is a filename pattern that is free to
    inspect locally but only observable on AWS as an import error.
    """
    want_py = "cpython-" + dict(zip(PIP_TARGET_ARGS[::2],
                                    PIP_TARGET_ARGS[1::2]))["--python-version"].replace(".", "")
    wrong = [f for f in BUILD.rglob("*.so")
             if "cpython-" in f.name and want_py not in f.name]
    if wrong:
        sys.exit(f"ERROR: package contains binaries for the wrong Python.\n"
                 f"Expected {want_py}, found e.g. {wrong[0].name}\n"
                 f"({len(wrong)} file(s)). They would fail to import on {RUNTIME}.")

    bad_arch = [f for f in BUILD.rglob("*.so")
                if "x86_64" in f.name and ARCHITECTURE != "x86_64"]
    if bad_arch:
        sys.exit(f"ERROR: package contains x86_64 binaries but ARCHITECTURE "
                 f"is {ARCHITECTURE}.")

    # NUMPY ABI PAIRING. An extension compiled against numpy 1.x aborts at
    # import under numpy 2.x with "_ARRAY_API not found", which is a
    # RUNTIME failure invisible in the file listing. onnxruntime gained
    # numpy 2 support in 1.19.0 (1.18.1 pinned numpy<2.0 explicitly), so
    # the pair is checkable from the two version numbers alone.
    ort_pin = next((d for d in DEPENDENCIES if "onnxruntime" in d), "")
    numpy_dir = BUILD / "numpy" / "version.py"
    numpy_major = None
    if numpy_dir.exists():
        match = re.search(r'version\s*=\s*[\'"](\d+)\.', numpy_dir.read_text())
        numpy_major = int(match.group(1)) if match else None
    if "==" in ort_pin and numpy_major is not None:
        ort_ver = tuple(int(x) for x in ort_pin.split("==")[1].split(".")[:2])
        if numpy_major >= 2 and ort_ver < (1, 19):
            sys.exit(f"ERROR: {ort_pin} was compiled against NumPy 1.x, but the "
                     f"package contains NumPy {numpy_major}.x.\nThe function would "
                     f"abort at import with '_ARRAY_API not found'.\n"
                     f"Use onnxruntime >= 1.19.0 (first release built for NumPy 2).")

    entry = HANDLER.split(".")[0] + ".py"
    if not (BUILD / entry).exists():
        sys.exit(f"ERROR: HANDLER is '{HANDLER}' but {entry} is not in the package.")

    for required in ("preprocess.py", "crops.py"):
        if not (BUILD / required).exists():
            sys.exit(f"ERROR: {required} missing from the package; "
                     f"{entry} imports it and would fail at import time.")


def _check_runtime_consistency() -> None:
    """RUNTIME, the pip --python-version and the glibc the tag implies must
    agree. They are three separate constants that silently disagree, and
    each disagreement costs a build+deploy cycle to discover.

    Also pins the runtime-to-glibc map, because the obvious assumption is
    wrong: python3.11 is Amazon Linux 2 (glibc 2.26), NOT AL2023. Only
    3.12 and later moved to AL2023 (2.34).
    """
    runtime_glibc = {"python3.11": 2.26, "python3.12": 2.34, "python3.13": 2.34}

    py = dict(zip(PIP_TARGET_ARGS[::2], PIP_TARGET_ARGS[1::2]))["--python-version"]
    if RUNTIME != f"python{py}":
        sys.exit(f"ERROR: RUNTIME is {RUNTIME} but wheels are being built for "
                 f"python{py}.\nThese must match or the runtime cannot import them.")

    tag = dict(zip(PIP_TARGET_ARGS[::2], PIP_TARGET_ARGS[1::2]))["--platform"]
    if not tag.endswith(ARCHITECTURE):
        sys.exit(f"ERROR: ARCHITECTURE is {ARCHITECTURE} but wheels are tagged "
                 f"{tag}.\nThe function could not import them.")

    needed = 2.17 if "2014" in tag else float(tag.split("_")[1] + "." + tag.split("_")[2])
    available = runtime_glibc.get(RUNTIME)
    if available is not None and needed > available:
        sys.exit(f"ERROR: wheels are tagged {tag} (needs glibc {needed}), but "
                 f"{RUNTIME}\nprovides only glibc {available}. Imports would fail "
                 f"at the first invocation.\nUse a newer runtime, or an older "
                 f"platform tag.")


def _model_files() -> list[Path]:
    """Every file the model needs at runtime: the .onnx plus any sidecars.

    Split out from _copy_model() so build_zip() can validate this before
    spending minutes on wheels -- and so the answer is derived from the
    graph rather than hardcoded, which is what trap 2 below requires.
    """
    if not MODEL_SRC.exists():
        sys.exit(f"ERROR: model not found at {MODEL_SRC}")
    try:
        import onnx
    except ImportError:
        sys.exit("ERROR: the `onnx` package is required to resolve the model's\n"
                 "external-data sidecar. Install it with:  pip install onnx")

    graph = onnx.load(str(MODEL_SRC), load_external_data=False).graph
    locations = {
        kv.value
        for init in graph.initializer
        for kv in init.external_data
        if kv.key == "location"
    }
    # IR-version gate. The deployed runtime is pinned by DEPENDENCIES, and
    # a model exported above what that runtime accepts deploys fine and
    # then fails at the first invocation -- a full build+upload cycle to
    # learn something checkable here in milliseconds. This is exactly the
    # failure seen on 2026-09-23 (IR 10 model vs onnxruntime 1.16.3).
    model = onnx.load(str(MODEL_SRC), load_external_data=False)
    if model.ir_version > MAX_SUPPORTED_IR:
        sys.exit(
            f"ERROR: {MODEL_SRC.name} is IR version {model.ir_version}, but the "
            f"pinned runtime\n({[d for d in DEPENDENCIES if 'onnxruntime' in d][0]}) "
            f"supports at most IR {MAX_SUPPORTED_IR}.\n"
            f"The build would succeed and every invocation would fail.\n\n"
            f"Fix: raise the onnxruntime pin in DEPENDENCIES (and MAX_SUPPORTED_IR),\n"
            f"or re-export the model at a lower opset."
        )

    files = [MODEL_SRC]
    for location in sorted(locations):
        sidecar = MODEL_SRC.parent / location
        if not sidecar.exists():
            sys.exit(f"ERROR: {MODEL_SRC.name} references external data "
                     f"'{location}', but {sidecar} does not exist.\n"
                     f"The model cannot load without it.")
        files.append(sidecar)
    if not locations:
        print("note: model is self-contained (no external data sidecar)")
    return files


def _copy_model() -> None:
    """Copy the ONNX model AND its external-data sidecar into the build.

    fire_mnv3.onnx does NOT contain its own weights. It was exported with
    ONNX external data, so the 306KB .onnx file is just the graph, and
    every initializer points at a separate 6MB blob on disk. Loading the
    graph without that blob beside it fails at InferenceSession() with:

        FAIL : External data path validation failed for initializer:
        features.0.0.weight ... External data path does not exist

    TWO traps here, both of which this function exists to avoid.

    1. The sidecar must travel WITH the model. An earlier version of this
       build copied only the .onnx and passed every local test, because
       the tests ran from the repo root where models/ happened to sit
       next to them. In Lambda's flat unzipped layout there is no models/
       directory and the load fails at the first invocation.

    2. The sidecar must keep its ORIGINAL filename. The location is
       baked into the .onnx graph as a literal string, and for
       fire_mnv3.onnx that string is "fire_mnv3_v4.onnx.data" -- the name
       of the checkpoint it was promoted from, NOT a name derived from
       the .onnx file. Renaming it to fire_mnv3.onnx.data (the obvious
       guess) breaks the reference just as thoroughly as omitting it.
       The name is read from the graph rather than assumed, so a future
       re-export under a different name keeps working.
    """
    for src in _model_files():
        shutil.copy2(src, BUILD / src.name)
        if src != MODEL_SRC:
            print(f"bundled external data: {src.name} ({src.stat().st_size / 1e6:.1f} MB)")


def _ensure_role() -> str:
    """Create (or reuse) the execution role. Logs only -- no S3, no VPC.

    Deliberately the AWS-managed basic-execution policy and nothing more:
    this function decodes a JPEG and runs a model, so any wider permission
    would be granting reach it has no use for.

    ROLE_ARN in the environment short-circuits all of this. That is the
    least-privilege path and the recommended one: create the role once in
    the console, and the deploying key then needs NO IAM permissions at
    all -- only Lambda. Granting a key IAMFullAccess lets it rewrite any
    permission in the account, including its own, which is far more reach
    than deploying one inference function warrants.
    """
    preset = os.environ.get("LAMBDA_ROLE_ARN")
    if preset:
        print(f"using preset role from LAMBDA_ROLE_ARN: {preset}")
        return preset

    iam = boto3.client("iam")
    trust = {"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"},
        "Action": "sts:AssumeRole"}]}
    try:
        role = iam.create_role(RoleName=ROLE_NAME, AssumeRolePolicyDocument=json.dumps(trust),
                               Description="FireWatch Stage 6 second-opinion inference")
        iam.attach_role_policy(RoleName=ROLE_NAME,
            PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole")
        print(f"created IAM role {ROLE_NAME}; waiting for propagation...")
        # IAM is eventually consistent: CreateFunction with a role AWS has
        # not propagated yet fails with an opaque InvalidParameterValue.
        time.sleep(10)
        return role["Role"]["Arn"]
    except iam.exceptions.EntityAlreadyExistsException:
        return iam.get_role(RoleName=ROLE_NAME)["Role"]["Arn"]


def _upload_via_s3(zip_bytes: bytes) -> dict:
    """Stage a >50MB zip in the project's existing bucket, then point Lambda at it."""
    import yaml
    with open(ROOT / "config.yaml") as f:
        bucket = yaml.safe_load(f)["aws"]["s3_bucket"]
    key = STAGED_ZIP_KEY
    boto3.client("s3", region_name=os.environ.get("AWS_DEFAULT_REGION")).put_object(
        Bucket=bucket, Key=key, Body=zip_bytes)
    print(f"staged build at s3://{bucket}/{key}")
    return {"S3Bucket": bucket, "S3Key": key}


def _preflight() -> None:
    """Check the deploying key can actually do this BEFORE the long build.

    Without this, a Lambda-denied key spends several minutes downloading
    wheels and assembling a 223MB package, then fails on the first API
    call. The failure is the same either way; finding out first is not.
    """
    try:
        _lambda_client().get_function(FunctionName=FUNCTION_NAME)
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code == "ResourceNotFoundException":
            return  # can reach Lambda, function simply does not exist yet
        if code in ("AccessDenied", "AccessDeniedException"):
            sys.exit(
                "ERROR: these AWS credentials cannot call Lambda.\n\n"
                "In the AWS console, attach AWSLambda_FullAccess to this IAM user.\n"
                "Then create the execution role once (IAM -> Roles -> Create role ->\n"
                "AWS service -> Lambda -> AWSLambdaBasicExecutionRole), name it\n"
                f"'{ROLE_NAME}', and export its ARN so no IAM permission is needed here:\n\n"
                "    export LAMBDA_ROLE_ARN=arn:aws:iam::<account>:role/" + ROLE_NAME + "\n"
            )
        raise


def deploy() -> None:
    _preflight()
    zip_path = build_zip()
    zip_bytes = zip_path.read_bytes()
    code = {"ZipFile": zip_bytes} if len(zip_bytes) < 50 * 1e6 else _upload_via_s3(zip_bytes)
    client = _lambda_client()

    try:
        existing = client.get_function(FunctionName=FUNCTION_NAME)["Configuration"]
        print(f"updating existing function {FUNCTION_NAME}...")
        client.update_function_code(FunctionName=FUNCTION_NAME, **code)
        client.get_waiter("function_updated_v2").wait(FunctionName=FUNCTION_NAME)

        # CONFIGURATION, NOT JUST CODE. update_function_code ships the zip
        # and nothing else: Runtime, Handler, MemorySize and Timeout keep
        # whatever the ORIGINAL create_function set. Every one of those is
        # declared as a constant at the top of this file, so an edit there
        # would silently never reach an already-deployed function.
        #
        # This is not hypothetical -- it cost a deploy cycle on 2026-09-23.
        # RUNTIME was changed python3.11 -> python3.12 to get a newer glibc,
        # the new python3.12 wheels uploaded fine, and the function kept
        # running python3.11, which then could not import them:
        #     _multiarray_umath.cpython-312-x86_64-linux-gnu.so
        #     seem incompatible with python 'cpython-311'
        #
        # Reconciling unconditionally (rather than diffing first) keeps the
        # constants above the single source of truth: whatever is deployed,
        # a deploy makes it match this file.
        drift = {k: (existing.get(k), v) for k, v in {
            "Runtime": RUNTIME, "Handler": HANDLER,
            "MemorySize": MEMORY_MB, "Timeout": TIMEOUT_S,
        }.items() if existing.get(k) != v}
        if drift:
            for key, (was, now) in drift.items():
                print(f"  config drift: {key} {was} -> {now}")
        client.update_function_configuration(
            FunctionName=FUNCTION_NAME, Runtime=RUNTIME, Handler=HANDLER,
            MemorySize=MEMORY_MB, Timeout=TIMEOUT_S,
        )
        client.get_waiter("function_updated_v2").wait(FunctionName=FUNCTION_NAME)
    except client.exceptions.ResourceNotFoundException:
        print(f"creating function {FUNCTION_NAME}...")
        client.create_function(
            FunctionName=FUNCTION_NAME, Runtime=RUNTIME, Role=_ensure_role(),
            Handler=HANDLER, Code=code, MemorySize=MEMORY_MB, Timeout=TIMEOUT_S,
            # Pinned, not left to the account default. The wheels are
            # downloaded for x86_64 (see PIP_TARGET_ARGS), so an arm64
            # function would fail to import them the same way a wrong
            # python version does. Relying on a default that AWS could
            # change, or that differs per account, is how that happens.
            Architectures=[ARCHITECTURE],
            Description="FireWatch cloud second opinion (advisory only; never gates the local alarm)",
        )
        client.get_waiter("function_active_v2").wait(FunctionName=FUNCTION_NAME)

    concurrency_note = _pin_concurrency(client)

    try:
        url = client.create_function_url_config(FunctionName=FUNCTION_NAME, AuthType="AWS_IAM")["FunctionUrl"]
    except client.exceptions.ResourceConflictException:
        url = client.get_function_url_config(FunctionName=FUNCTION_NAME)["FunctionUrl"]

    print("\n" + "=" * 68)
    print(f"deployed: {FUNCTION_NAME}")
    print(f"endpoint: {url}")
    print(f"  memory {MEMORY_MB}MB | timeout {TIMEOUT_S}s | {concurrency_note}")
    print("\nAuthType=AWS_IAM: callers must sign requests with SigV4.")
    print("Put this in config.yaml under cloud.second_opinion.endpoint")
    print("\nWHEN THE DEMO IS DONE, tear it all down with:")
    print("    python scripts/deploy_lambda.py --delete")
    print("=" * 68)


def _pin_concurrency(client) -> str:  # noqa: ANN001 (boto3 client)
    """Pin reserved concurrency, tolerating a small account quota.

    Reserving N for this function REMOVES N from the account's shared
    unreserved pool, and AWS refuses to let that pool drop below 10. On a
    default account (limit 1000) reserving 1 is invisible. On a NEW
    account the limit is 10, the whole quota is the minimum, and the same
    call fails with InvalidParameterValueException -- which is what
    happened here on 2026-09-23 (account limit: 10).

    Not fatal, and deliberately not retried with a smaller number: there
    is no smaller number. Reserved concurrency is the AWS-side backstop
    against a runaway caller, so losing it matters, but it is the SECOND
    line of defence. The first -- rising-edge triggering, a cooldown and
    a session invocation counter in cloud/second_opinion.py -- is
    client-side and unaffected. An account capped at 10 concurrent
    executions is also its own ceiling: the blast radius of a runaway
    loop is bounded at 10 in-flight invocations by the account quota
    itself, which is the protection this call was buying.

    Raising the account quota is a support-ticket request to AWS. Not
    worth filing for a demo; worth knowing if this ever runs for real.
    """
    try:
        client.put_function_concurrency(
            FunctionName=FUNCTION_NAME,
            ReservedConcurrentExecutions=RESERVED_CONCURRENCY)
        return f"reserved concurrency {RESERVED_CONCURRENCY}"
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "InvalidParameterValueException":
            raise
        limit = client.get_account_settings()["AccountLimit"]["ConcurrentExecutions"]
        print(f"\nnote: could not reserve concurrency -- this account's total limit "
              f"is {limit:.0f},\n      and AWS keeps 10 unreserved at minimum. The "
              f"account quota itself\n      now bounds concurrency; client-side "
              f"guards are unaffected.")
        return f"unreserved (account limit {limit:.0f})"


def delete() -> None:
    """Remove every resource this script creates. Safe to run twice."""
    client = _lambda_client()
    try:
        client.delete_function_url_config(FunctionName=FUNCTION_NAME)
        print("deleted function URL")
    except ClientError:
        pass
    try:
        client.delete_function(FunctionName=FUNCTION_NAME)
        print(f"deleted function {FUNCTION_NAME}")
    except ClientError as exc:
        print(f"function not deleted ({exc.response['Error']['Code']}) — may already be gone")

    iam = boto3.client("iam")
    try:
        iam.detach_role_policy(RoleName=ROLE_NAME,
            PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole")
        iam.delete_role(RoleName=ROLE_NAME)
        print(f"deleted IAM role {ROLE_NAME}")
    except ClientError as exc:
        print(f"role not deleted ({exc.response['Error']['Code']}) — may already be gone")

    # The >50MB build is staged in S3 by _upload_via_s3() and outlives the
    # function. ~84MB is fractions of a cent a month, but "nothing left
    # billing" below should be literally true, and forgotten objects are
    # how forgotten costs start.
    import yaml
    bucket = yaml.safe_load((ROOT / "config.yaml").read_text())["aws"]["s3_bucket"]
    try:
        boto3.client("s3", region_name=os.environ.get("AWS_DEFAULT_REGION")).delete_object(
            Bucket=bucket, Key=STAGED_ZIP_KEY)
        print(f"deleted staged build s3://{bucket}/{STAGED_ZIP_KEY}")
    except ClientError as exc:
        print(f"staged build not deleted ({exc.response['Error']['Code']})")
    print("\nteardown complete — nothing left running, nothing left billing.")


def test_invoke(image: str) -> None:
    """Invoke the deployed function with a real frame and print the verdict.

    Uses the boto3 Invoke API rather than the URL so no SigV4 request
    signing is needed here -- the credentials in the environment are
    already what boto3 signs with.
    """
    import base64
    raw = Path(image).read_bytes()
    payload = json.dumps({"body": json.dumps({"jpeg_b64": base64.b64encode(raw).decode()})})
    started = time.perf_counter()
    resp = _lambda_client().invoke(FunctionName=FUNCTION_NAME, Payload=payload.encode())
    elapsed = (time.perf_counter() - started) * 1000
    result = json.loads(resp["Payload"].read())

    # A Lambda-LEVEL failure (unhandled exception, import error, OOM,
    # timeout) never reaches handler.lambda_handler's try/except, so the
    # payload is AWS's {errorMessage, errorType, stackTrace} shape rather
    # than ours. Indexing result["body"] there raises KeyError and buries
    # the actual cause -- which is exactly what happened on 2026-09-23,
    # hiding the real error behind a traceback in this script.
    if "FunctionError" in resp or "errorMessage" in result:
        print(f"round trip {elapsed:.0f} ms | LAMBDA ERROR "
              f"({resp.get('FunctionError', 'Unhandled')})\n")
        print(f"  {result.get('errorType', '?')}: {result.get('errorMessage', result)}")
        for line in result.get("stackTrace", []):
            print(f"    {line.rstrip()}")
        print("\nFull logs:  aws logs tail /aws/lambda/" + FUNCTION_NAME + " --since 10m")
        sys.exit(1)

    print(f"round trip {elapsed:.0f} ms | status {result.get('statusCode')}")
    body = json.loads(result["body"]) if "body" in result else result
    print(json.dumps(body, indent=2))

    # The number that matters: the deployed verdict must match local
    # inference. A drift here means the cloud/local onnxruntime gap is
    # NOT benign, which would invalidate the agree/disagree display.
    if body.get("ok") and "p_fire" in body:
        print(f"\n  p_fire {body['p_fire']:.12f}")
        print("  compare against local inference for the same frame.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build-only", action="store_true", help="build the zip, deploy nothing")
    ap.add_argument("--delete", action="store_true", help="tear down function, URL and role")
    ap.add_argument("--test", metavar="IMAGE", nargs="?", const="data/val/fire/AoF04017.jpg",
                    help="invoke the deployed function with a JPEG")
    args = ap.parse_args()

    if args.delete:
        delete()
    elif args.build_only:
        build_zip()
    elif args.test:
        test_invoke(args.test)
    else:
        deploy()


if __name__ == "__main__":
    main()
