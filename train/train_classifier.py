"""Fine-tune MobileNetV3-Small into the FireWatch 3-class classifier.

WHY MobileNetV3-Small and not something bigger: the deployment target is a
laptop CPU running ONNX Runtime at >= 5 FPS alongside a live camera loop
(plan.md 4.3, info.md 4.3). MobileNetV3-Small is ~2.5M parameters and was
designed (via hardware-aware architecture search) specifically for fast
mobile/CPU inference. A ResNet-50 (~25M params) might add a point or two of
accuracy but would blow the FPS budget at demo time. This is the params-vs-FPS
trade: we buy real-time edge inference with a model whose ImageNet-pretrained
features are still strong enough to transfer-learn fire/smoke in one session.

WHY transfer learning at all: 21,722 images is far too few to learn general
visual features (edges, textures, colour gradients) from scratch. ImageNet
pretraining already learned those on 1.2M images; we only need to teach the
network the last step -- mapping those features to neutral/smoke/fire.

Deviation from plan.md 8 Day 2 (recorded in logs.md Phase 2): training runs
LOCALLY on the developer's M4 Pro via PyTorch's MPS backend, not on Colab.
"""

import argparse
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader
from torchvision import datasets, models, transforms

from metrics_report import (confusion_matrix, per_class_metrics, print_metrics_table,
                            save_confusion_matrix_plot, save_training_curves)

SEED = 42
NUM_CLASSES = 3
# ImageNet channel statistics. The pretrained weights were trained on inputs
# normalized with these exact numbers, so our inputs must match or the
# pretrained filters see out-of-distribution values and transfer degrades.
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]
# Stage 2 LR is 20x lower than stage 1, and that gap is the whole point:
# stage 1 trains a randomly-initialised head, which needs big steps to become
# useful at all. Stage 2 fine-tunes pretrained ImageNet filters, which are
# already good -- a stage-1-sized LR would overwrite them (catastrophic
# forgetting) instead of gently nudging them toward fire/smoke textures.
STAGE1_LR = 1e-3
STAGE2_LR = 5e-5
FREEZE_EPOCHS = 2  # stage 1 length: epochs 1-2 train the new head only
# Batch size: MobileNetV3-Small at 224px is tiny (activations a few hundred MB
# at this size), and the M4 Pro's 24GB unified memory gives far more headroom
# than a Colab T4's 16GB dedicated VRAM -- so 128 instead of a T4-typical 32/64.
# Caveat: "unified" means the GPU shares that 24GB with the OS and every open
# app, so the usable ceiling is softer than a discrete GPU's -- another reason
# not to chase the theoretical maximum batch size.
BATCH_SIZE = 128


def set_seeds(seed: int) -> None:
    """Seed every RNG in play (info.md 3.3 -- reproducibility is graded).

    Honesty caveat: torch.manual_seed covers MPS tensor init, but MPS does not
    offer CUDA's torch.use_deterministic_algorithms guarantees -- some GPU
    kernels reduce in nondeterministic order, so two runs may differ in the
    last decimal places even with identical seeds. Seeding still fixes the
    data order and augmentation stream, which is most of the run-to-run
    variance; bit-exact repeatability is only promised on CPU.
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def select_device(force_cpu: bool) -> torch.device:
    """MPS (Apple-silicon GPU) if available, else CPU. No CUDA branch: no NVIDIA GPU here."""
    if force_cpu:
        print("Device: CPU (forced via --force-cpu)")
        return torch.device("cpu")
    if torch.backends.mps.is_available():
        print("Device: MPS (Apple-silicon GPU)")
        return torch.device("mps")
    print("Device: CPU (MPS not available on this machine/PyTorch build)")
    return torch.device("cpu")


def build_transforms() -> tuple[transforms.Compose, transforms.Compose]:
    """Return (train_transform, val_transform) -- deliberately DIFFERENT.

    Train gets augmentation: each epoch the model sees randomly cropped,
    flipped, colour-shifted variants of every image, which teaches robustness
    (a fire is a fire whether it's left-of-frame, mirrored, or under a warmer
    white balance) and fights overfitting on our modest dataset.

    Val gets NONE of that -- plain resize + normalize only -- because val's job
    is to estimate deployment accuracy, and at deployment the edge loop feeds
    the model plain resized webcam frames (plan.md Day 3: frame -> 224x224
    normalized tensor). Augmenting val would corrupt that signal: metrics
    would describe a jittered world no user ever shows the model. Direct
    224x224 resize (not resize-256-then-center-crop) to mirror exactly what
    edge/vision.py will do to frames.
    """
    train_tf = transforms.Compose([
        # Random crop of 60-100% of the image, resized to 224: simulates the
        # fire being nearer/farther/off-centre, the dominant variation a fixed
        # camera will actually encounter.
        transforms.RandomResizedCrop(224, scale=(0.6, 1.0)),
        transforms.RandomHorizontalFlip(),
        # Mild colour jitter: robustness to lighting/white-balance shifts.
        # Kept mild on purpose -- hue is what separates fire from steam and
        # sunsets, so aggressive hue jitter would destroy the signal we need.
        transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2, hue=0.02),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])
    val_tf = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])
    return train_tf, val_tf


def build_model() -> nn.Module:
    """MobileNetV3-Small pretrained on ImageNet, with a fresh 3-class head.

    The stock classifier ends in Linear(1024 -> 1000) for ImageNet's classes.
    Those 1000 outputs mean nothing here, so we discard that layer entirely and
    attach a new Linear(1024 -> 3). Only this layer starts from random
    initialisation -- everything before it keeps its pretrained weights.
    """
    model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.IMAGENET1K_V1)
    model.classifier[3] = nn.Linear(model.classifier[3].in_features, NUM_CLASSES)
    return model


def set_backbone_frozen(model: nn.Module, frozen: bool) -> None:
    """(Un)freeze everything except the final 3-class layer.

    "Freezing" mechanically means requires_grad=False: autograd then skips
    computing gradients for those weights and the optimizer never updates
    them. During stage 1 the pretrained features act as a fixed feature
    extractor while only the new random head learns. Without this, the random
    head's large, noisy early gradients would backpropagate into (and scramble)
    the pretrained filters before the head has learned anything sensible.
    """
    for name, param in model.named_parameters():
        param.requires_grad = (not frozen) or name.startswith("classifier.3")


def run_epoch(model: nn.Module, loader: DataLoader, device: torch.device,
              criterion: nn.Module, optimizer: torch.optim.Optimizer | None) -> tuple[float, float]:
    """One pass over a loader. Trains if an optimizer is given, else evaluates.

    Returns (mean loss, accuracy). eval mode also matters beyond gradients:
    it switches BatchNorm to its running statistics and disables Dropout, so
    val numbers reflect the network as it will behave at inference time.
    """
    training = optimizer is not None
    model.train(training)
    total_loss, correct, seen = 0.0, 0, 0
    with torch.set_grad_enabled(training):
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)
            logits = model(images)
            loss = criterion(logits, labels)
            if training:
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
            total_loss += loss.item() * labels.size(0)
            correct += (logits.argmax(dim=1) == labels).sum().item()
            seen += labels.size(0)
    return total_loss / seen, correct / seen


def evaluate_predictions(model: nn.Module, loader: DataLoader, device: torch.device) -> tuple[np.ndarray, np.ndarray]:
    """Collect (true, predicted) label arrays over a loader, for the confusion matrix."""
    model.eval()
    trues, preds = [], []
    with torch.no_grad():
        for images, labels in loader:
            logits = model(images.to(device))
            preds.append(logits.argmax(dim=1).cpu().numpy())
            trues.append(labels.numpy())
    return np.concatenate(trues), np.concatenate(preds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune MobileNetV3-Small for FireWatch.")
    parser.add_argument("--epochs", type=int, default=12, help="total epochs across both stages")
    parser.add_argument("--force-cpu", action="store_true", help="skip MPS even if available")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--checkpoint", type=Path, default=Path("models/fire_mnv3_best.pt"))
    args = parser.parse_args()

    set_seeds(SEED)
    device = select_device(args.force_cpu)

    train_tf, val_tf = build_transforms()
    # ImageFolder assigns class indices ALPHABETICALLY over folder names, so
    # fire=0, neutral=1, smoke=2 -- NOT the neutral/smoke/fire order the class
    # names are usually spoken in. Everything downstream (checkpoint, ONNX
    # export, edge loop) must use this mapping, so it is saved into the
    # checkpoint rather than assumed anywhere.
    train_ds = datasets.ImageFolder(args.data_dir / "train", transform=train_tf)
    val_ds = datasets.ImageFolder(args.data_dir / "val", transform=val_tf)
    assert train_ds.class_to_idx == val_ds.class_to_idx, "train/val class folders disagree"
    assert set(train_ds.classes) == {"neutral", "smoke", "fire"}, f"unexpected classes: {train_ds.classes}"
    print(f"Class mapping (alphabetical, from actual folders): {train_ds.class_to_idx}")
    print(f"Train: {len(train_ds)} images, Val: {len(val_ds)} images")

    loader_kwargs = dict(batch_size=BATCH_SIZE, num_workers=6, persistent_workers=True)
    train_loader = DataLoader(train_ds, shuffle=True, **loader_kwargs)
    val_loader = DataLoader(val_ds, shuffle=False, **loader_kwargs)

    model = build_model().to(device)
    criterion = nn.CrossEntropyLoss()

    # --- Stage 1: frozen backbone, train only the new head at a high LR. ---
    set_backbone_frozen(model, frozen=True)
    # filter(): hand the optimizer only trainable params, so frozen weights
    # can't be touched even by weight decay.
    optimizer = torch.optim.AdamW(
        filter(lambda p: p.requires_grad, model.parameters()), lr=STAGE1_LR)
    # Cosine decay per stage: LR glides smoothly from its peak to ~0 over the
    # stage instead of dropping in steps -- large steps early when far from a
    # minimum, tiny careful steps late. Each stage gets its own schedule since
    # the two stages have different peak LRs.
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=FREEZE_EPOCHS)

    history: dict[str, list[float]] = {k: [] for k in ("train_loss", "train_acc", "val_loss", "val_acc")}
    best_val_acc, training_start = 0.0, time.time()

    for epoch in range(1, args.epochs + 1):
        if epoch == FREEZE_EPOCHS + 1:
            # --- Stage 2: unfreeze everything, continue end-to-end at low LR.
            # A fresh optimizer is REQUIRED here, not just new requires_grad
            # flags: the stage-1 optimizer never registered the backbone
            # params, and its LR is 20x too hot for pretrained weights.
            print(f"--- Stage 2: unfreezing backbone, LR {STAGE1_LR} -> {STAGE2_LR} ---")
            set_backbone_frozen(model, frozen=False)
            optimizer = torch.optim.AdamW(model.parameters(), lr=STAGE2_LR)
            scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
                optimizer, T_max=args.epochs - FREEZE_EPOCHS)

        epoch_start = time.time()
        try:
            train_loss, train_acc = run_epoch(model, train_loader, device, criterion, optimizer)
            val_loss, val_acc = run_epoch(model, val_loader, device, criterion, None)
        except RuntimeError as exc:
            # MPS is newer than CUDA and some ops lack MPS kernels; a mid-run
            # RuntimeError on the mps device is most likely that. Fail LOUDLY
            # -- never silently fall back to CPU, which is several times
            # slower and the developer must knowingly choose it.
            if device.type == "mps":
                print("\n[ERROR] Training failed on the MPS backend. This is most likely an")
                print("MPS-specific unsupported operation (Apple-GPU PyTorch support is newer")
                print("and less complete than CUDA/CPU). The failing op was NOT run on CPU.")
                print(f"Underlying error: {exc}")
                print("Options: report this exact error to the developer, or re-run with")
                print("--force-cpu (much slower, but every op is supported).")
                sys.exit(1)
            raise

        scheduler.step()  # after the epoch: cosine decay is per-epoch here, not per-batch
        stage = 1 if epoch <= FREEZE_EPOCHS else 2
        print(f"Epoch {epoch:2d}/{args.epochs} [stage {stage}] "
              f"train loss {train_loss:.4f} acc {train_acc:.4f} | "
              f"val loss {val_loss:.4f} acc {val_acc:.4f} | {time.time() - epoch_start:.1f}s")
        for key, value in zip(history, (train_loss, train_acc, val_loss, val_acc)):
            history[key].append(value)

        # Keep the BEST epoch by val accuracy, not the last: late fine-tuning
        # epochs can overfit, and we want the deployed model to be the one
        # that generalised best, wherever in the run it occurred.
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
            torch.save({"model_state_dict": model.state_dict(), "epoch": epoch,
                        "val_acc": val_acc, "class_to_idx": train_ds.class_to_idx},
                       args.checkpoint)

    print(f"\nTotal training wall-clock time: {time.time() - training_start:.1f}s")
    print(f"Best val accuracy {best_val_acc:.4f}; checkpoint: {args.checkpoint}")

    # --- Final evaluation on the BEST checkpoint (not necessarily the final epoch). ---
    model.load_state_dict(torch.load(args.checkpoint, map_location=device)["model_state_dict"])
    trues, preds = evaluate_predictions(model, val_loader, device)
    idx_to_class = {i: c for c, i in train_ds.class_to_idx.items()}
    cm = confusion_matrix(trues, preds, NUM_CLASSES)
    metrics = per_class_metrics(cm)
    print_metrics_table(metrics, idx_to_class)
    save_confusion_matrix_plot(cm, idx_to_class, Path("eval/confusion_matrix.png"))
    save_training_curves(history, Path("eval/training_curves.png"))
    print("Saved eval/confusion_matrix.png and eval/training_curves.png")

    # --- The single most important number in this run (info.md 4.1): fire
    # recall >= 0.95 is a BLOCK bar. Missing a real fire is the worst possible
    # failure this system can have, so this check is explicit and loud.
    fire_recall = metrics[train_ds.class_to_idx["fire"]]["recall"]
    if fire_recall >= 0.95:
        print(f"\nFIRE RECALL {fire_recall:.4f} >= 0.95 -- PASS (info.md 4.1 block bar)")
    else:
        print(f"\nFIRE RECALL {fire_recall:.4f} < 0.95 -- FAIL (info.md 4.1 block bar)")
        print("Do NOT proceed to Phase 3. Per info.md 7, stop and report -- do not")
        print("silently retrain with different hyperparameters.")
        sys.exit(2)


if __name__ == "__main__":
    main()
