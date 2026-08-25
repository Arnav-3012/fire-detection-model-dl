"""Export the best FireWatch checkpoint to ONNX and verify it faithfully.

WHY ONNX at all: the edge loop (plan.md 4.3) runs on a laptop CPU, and ONNX
Runtime executes this model 3-5x faster there than raw PyTorch -- the
difference between meeting and missing the >= 5 FPS block bar (info.md 4.3).
ONNX also makes the deployed artifact framework-independent: edge/vision.py
needs only onnxruntime, not a full PyTorch install, which matches the
edge-first design (small dependency footprint, no training stack at demo
time).

WHY verification matters: export is a TRANSLATION of the compute graph, and
translations can be subtly wrong (op version mismatches, layout differences)
while still producing plausible-looking numbers. Comparing ONNX Runtime
output against the original PyTorch model on REAL validation images -- not
random tensors, which may not exercise the same activation ranges as real
photos -- proves the artifact we ship is the model we measured. Skipping this
check risks silently deploying a model whose fire recall was never actually
evaluated.
"""

import argparse
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
from torch import nn
from torchvision import datasets, models, transforms

# Must match training exactly -- a preprocessing mismatch here would make the
# comparison meaningless (and is the classic cause of "ONNX differs" bugs,
# per plan.md's troubleshooting table).
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]
NUM_CLASSES = 3
TOLERANCE = 1e-4
N_VERIFY_IMAGES = 32


def load_model(checkpoint_path: Path) -> tuple[nn.Module, dict[str, int]]:
    """Rebuild the architecture and load the best checkpoint's weights (CPU).

    Export happens on CPU deliberately: the deployment target is CPU ONNX
    Runtime, and exporting from the CPU graph avoids any MPS-specific op
    quirks leaking into the artifact.
    """
    model = models.mobilenet_v3_small(weights=None)  # weights come from our checkpoint
    model.classifier[3] = nn.Linear(model.classifier[3].in_features, NUM_CLASSES)
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()  # inference behaviour (BatchNorm running stats, no Dropout) is what gets exported
    print(f"Loaded {checkpoint_path} (epoch {checkpoint['epoch']}, val_acc {checkpoint['val_acc']:.4f})")
    print(f"Class mapping: {checkpoint['class_to_idx']}")
    return model, checkpoint["class_to_idx"]


def export(model: nn.Module, out_path: Path) -> None:
    """Export to ONNX with a dynamic batch axis.

    The dummy input only defines shapes/dtypes for tracing -- its values are
    irrelevant. dynamic_axes frees axis 0 so the same file serves the edge
    loop (batch of 1 frame) and any batched offline evaluation, instead of
    baking in a fixed batch size.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.randn(1, 3, 224, 224)
    torch.onnx.export(
        model, dummy, str(out_path),
        input_names=["input"], output_names=["logits"],
        dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
    )
    print(f"Exported to {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")


def verify(model: nn.Module, onnx_path: Path, val_dir: Path) -> bool:
    """Compare PyTorch vs ONNX Runtime outputs on real validation images.

    Real images, same preprocessing as val at training time, so the comparison
    exercises exactly the tensor distribution the deployed model will see.
    Comparison is on raw logits (pre-softmax): softmax would shrink absolute
    differences and could mask a real divergence.
    """
    val_tf = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])
    val_ds = datasets.ImageFolder(val_dir, transform=val_tf)
    # Evenly spaced indices sample all three classes (ImageFolder orders by
    # class folder), rather than N images of only the first class.
    indices = np.linspace(0, len(val_ds) - 1, N_VERIFY_IMAGES, dtype=int)
    batch = torch.stack([val_ds[i][0] for i in indices])

    with torch.no_grad():
        torch_logits = model(batch).numpy()

    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    onnx_logits = session.run(["logits"], {"input": batch.numpy()})[0]

    max_diff = float(np.abs(torch_logits - onnx_logits).max())
    print(f"Verified on {len(indices)} real val images; max |PyTorch - ONNX| logit diff: {max_diff:.2e}")
    if max_diff <= TOLERANCE:
        print(f"ONNX VERIFICATION -- PASS (max diff {max_diff:.2e} <= {TOLERANCE})")
        return True
    print(f"ONNX VERIFICATION -- FAIL (max diff {max_diff:.2e} > {TOLERANCE})")
    print("Do not deploy this artifact; the exported graph does not match the trained model.")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Export FireWatch model to ONNX and verify.")
    parser.add_argument("--checkpoint", type=Path, default=Path("models/fire_mnv3_best.pt"))
    parser.add_argument("--output", type=Path, default=Path("models/fire_mnv3.onnx"))
    parser.add_argument("--val-dir", type=Path, default=Path("data/val"))
    args = parser.parse_args()

    model, _ = load_model(args.checkpoint)
    export(model, args.output)
    if not verify(model, args.output, args.val_dir):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
