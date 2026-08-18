"""Environment verification for FireWatch.

Imports every major dependency from requirements.txt and prints a
pass/fail table. Run after setup.sh / setup.ps1, before starting real
work. See info.md section 5. Exits non-zero if anything fails.
"""

import sys
from pathlib import Path

# Maps the requirements.txt distribution name to its actual import name,
# where they differ (PyPI name != module name).
PACKAGE_IMPORTS = {
    "torch": "torch",
    "torchvision": "torchvision",
    "onnx": "onnx",
    "onnxruntime": "onnxruntime",
    "opencv-python": "cv2",
    "numpy": "numpy",
    "pandas": "pandas",
    "pyserial": "serial",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "langgraph": "langgraph",
    "langchain-core": "langchain_core",
    "groq": "groq",
    "boto3": "boto3",
    "paho-mqtt": "paho.mqtt.client",
    "streamlit": "streamlit",
    "python-dotenv": "dotenv",
    "pyyaml": "yaml",
    "requests": "requests",
}


def check_python_version() -> tuple[bool, str]:
    major, minor = sys.version_info[:2]
    ok = (major, minor) in ((3, 10), (3, 11))
    return ok, f"{major}.{minor} (need 3.10 or 3.11)"


def check_package(import_name: str) -> tuple[bool, str]:
    try:
        module = __import__(import_name)
        version = getattr(module, "__version__", "unknown")
        return True, str(version)
    except ImportError as e:
        return False, str(e)


def check_config_yaml() -> tuple[bool, str]:
    import yaml

    config_path = Path(__file__).parent.parent / "config.yaml"
    try:
        with open(config_path) as f:
            yaml.safe_load(f)
        return True, str(config_path)
    except Exception as e:
        return False, str(e)


def print_table(rows: list[tuple[str, bool, str]]) -> None:
    name_width = max(len(r[0]) for r in rows) + 2
    detail_width = max(len(r[2]) for r in rows) + 2
    header = f"{'CHECK':<{name_width}}{'STATUS':<8}{'DETAIL':<{detail_width}}"
    print(header)
    print("-" * len(header))
    for name, ok, detail in rows:
        status = "PASS" if ok else "FAIL"
        print(f"{name:<{name_width}}{status:<8}{detail:<{detail_width}}")


def main() -> int:
    rows: list[tuple[str, bool, str]] = []

    py_ok, py_detail = check_python_version()
    rows.append(("python", py_ok, py_detail))

    for dist_name, import_name in PACKAGE_IMPORTS.items():
        ok, detail = check_package(import_name)
        rows.append((dist_name, ok, detail))

    cfg_ok, cfg_detail = check_config_yaml()
    rows.append(("config.yaml", cfg_ok, cfg_detail))

    print_table(rows)
    print()

    if all(ok for _, ok, _ in rows):
        print("ALL PASS")
        return 0

    failed = [name for name, ok, _ in rows if not ok]
    print(f"FAILED: {', '.join(failed)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
