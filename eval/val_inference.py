"""Shared helper: load the best checkpoint and run inference over data/val.

Factored out of inspect_misclassified.py so threshold_sweep.py (and any
future diagnostic script) doesn't duplicate the model-loading and
val-set-inference logic -- both need the exact same thing: every val image's
true label and full 3-class probability distribution.
"""

from pathlib import Path

import numpy as np
import torch
from torch import nn
from torchvision import datasets, models, transforms

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]
NUM_CLASSES = 3
CHECKPOINT_PATH = Path("models/fire_mnv3_best.pt")
VAL_DIR = Path("data/val")


def load_model(checkpoint_path: Path = CHECKPOINT_PATH) -> tuple[nn.Module, dict[str, int]]:
    model = models.mobilenet_v3_small(weights=None)
    model.classifier[3] = nn.Linear(model.classifier[3].in_features, NUM_CLASSES)
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    print(f"Loaded {checkpoint_path} (epoch {checkpoint['epoch']}, val_acc {checkpoint['val_acc']:.4f})")
    return model, checkpoint["class_to_idx"]


def run_inference(model: nn.Module, class_to_idx: dict[str, int]):
    """Run the val set through the model, returning (probs, true_labels, image_paths).

    Same val transform as training (plain resize + normalize, no augmentation)
    -- must match exactly, or the model is scored on a different distribution
    than it was validated on during training.
    """
    val_tf = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])
    val_ds = datasets.ImageFolder(VAL_DIR, transform=val_tf)
    assert val_ds.class_to_idx == class_to_idx, "val folder class mapping disagrees with checkpoint"

    loader = torch.utils.data.DataLoader(val_ds, batch_size=128, shuffle=False, num_workers=4)
    all_probs, all_labels = [], []
    with torch.no_grad():
        for images, labels in loader:
            logits = model(images)
            probs = torch.softmax(logits, dim=1)
            all_probs.append(probs.numpy())
            all_labels.append(labels.numpy())

    probs = np.concatenate(all_probs)
    labels = np.concatenate(all_labels)
    # val_ds.samples preserves iteration order (shuffle=False), so this lines
    # up 1:1 with probs/labels.
    paths = [Path(p) for p, _ in val_ds.samples]
    return probs, labels, paths
