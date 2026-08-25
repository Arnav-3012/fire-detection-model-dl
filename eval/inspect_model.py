"""Model inspection and documentation tool for FireWatch's fire/smoke/neutral classifier.

WHAT THIS SCRIPT IS FOR: this is a diagnostic/report-writing aid, not part of
the training or evaluation pipeline. It exists so the developer can explain,
in a viva or a written report, WHAT the trained model actually looks like
inside -- its structure, its parameter budget, whether its learned weights
look numerically sane, what its internal feature maps actually respond to on
real fire/smoke/neutral images, and (via Grad-CAM) WHERE in the image it is
actually looking when it makes a decision. It does not retrain, does not
touch train_classifier.py or config.yaml, and does not change any metric
already recorded in logs.md.

Run with: conda run -n firewatch python eval/inspect_model.py

All outputs specific to this script live under eval/model_understanding/ --
kept separate from eval/confusion_matrix.png, eval/training_curves.png,
eval/class_balance.png and other files that are actual phase deliverables
(plan.md 4.2, info.md 5), not exploratory tooling output.

Produces:
  eval/model_understanding/architecture.txt      -- full printed model structure
  eval/model_understanding/architecture_diagram.png -- simplified stem->blocks->head diagram
  eval/model_understanding/feature_maps_fire.png    -- early + late layer activations
  eval/model_understanding/feature_maps_smoke.png   -- same, smoke image
  eval/model_understanding/feature_maps_neutral.png -- same, neutral image
  eval/model_understanding/gradcam_fire.png      -- Grad-CAM overlay, fire image
  eval/model_understanding/gradcam_smoke.png     -- same, smoke image
  eval/model_understanding/gradcam_neutral.png   -- same, neutral image

The image used per class (for both feature maps and Grad-CAM) is selected by
running inference over ALL of that class's data/val/<class>/ images and
picking the one the model classified correctly with the HIGHEST confidence --
see select_representative_image() -- not just the first file found. This
gives a genuine "textbook example" per class, appropriate for a report or
viva, rather than an arbitrary or (as before) sometimes-misclassified image.
"""

import random
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import torch
import torch.nn.functional as F
from torch import nn
from torchvision import models, transforms
from PIL import Image

from val_inference import load_model as load_model_for_inference, run_inference

SEED = 42
CHECKPOINT_PATH = Path("models/fire_mnv3_best.pt")
DATA_VAL_DIR = Path("data/val")
EVAL_DIR = Path("eval")
MODEL_UNDERSTANDING_DIR = EVAL_DIR / "model_understanding"

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

# How many channels to show per feature-map grid. The real layers have far
# more channels than this (e.g. 576 in the last block) -- showing all of them
# would be an unreadable wall of thumbnails, so we sample a fixed, reproducible
# subset. This is a display choice only; it does not change what the model
# computes.
N_CHANNELS_TO_SHOW = 12


def set_seed(seed: int) -> None:
    """Match train_classifier.py's seeding practice (info.md 3.3)."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def load_model(checkpoint_path: Path) -> tuple[nn.Module, dict[str, int]]:
    """Rebuild the exact architecture used in training and load trained weights.

    The checkpoint only stores state_dict + metadata (see train_classifier.py),
    not the architecture itself, so we must reconstruct the same
    MobileNetV3-Small-with-3-class-head structure before loading weights into
    it. This mirrors build_model() in train_classifier.py exactly, on purpose --
    if that function ever changes, this script must change with it.
    """
    model = models.mobilenet_v3_small(weights=None)  # no need to re-download ImageNet weights, we're loading our own
    model.classifier[3] = nn.Linear(model.classifier[3].in_features, 3)

    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()  # inference mode: fixes BatchNorm stats, disables Dropout

    class_to_idx = checkpoint["class_to_idx"]
    print(f"Loaded checkpoint: {checkpoint_path}")
    print(f"  Saved at epoch {checkpoint['epoch']}, val_acc {checkpoint['val_acc']:.4f}")
    print(f"  Class mapping (alphabetical -- see train_classifier.py): {class_to_idx}")
    return model, class_to_idx


# ---------------------------------------------------------------------------
# PART 1 -- Architecture summary
# ---------------------------------------------------------------------------

def print_and_save_architecture(model: nn.Module, out_path: Path) -> None:
    """Print the full module tree, and save the identical text to a file.

    print(model) walks every registered submodule (nn.Conv2d, nn.BatchNorm2d,
    nn.Hardswish, etc.) and prints its type and constructor arguments in
    nested form -- this is PyTorch's built-in structural summary, not
    something we compute ourselves. It is the clearest single artifact for
    "what does this network actually consist of".
    """
    arch_str = str(model)
    print("\n" + "=" * 70)
    print("PART 1a -- FULL MODEL ARCHITECTURE")
    print("=" * 70)
    print(arch_str)

    out_path.write_text(arch_str + "\n")
    print(f"\n[saved] {out_path}")


def count_parameters(module: nn.Module) -> tuple[int, int]:
    """Return (total_params, trainable_params) for a module.

    "Trainable" here means requires_grad=True as the checkpoint left it. Since
    the checkpoint was saved AFTER stage 2 (backbone unfrozen, per
    train_classifier.py's set_backbone_frozen(model, frozen=False) at
    epoch == FREEZE_EPOCHS + 1), every parameter in the loaded model reports
    trainable=True right now -- that is the FINAL state, not the state during
    stage 1. During stage 1 (epochs 1-2), everything except classifier.3 (the
    new 3-class head) had requires_grad=False and did not receive gradient
    updates; the pretrained ImageNet backbone acted as a fixed feature
    extractor while only the head learned from a random start. From epoch 3
    onward (stage 2), every parameter shown here as "trainable" was actually
    being updated, at a 20x lower learning rate (STAGE2_LR=5e-5 vs
    STAGE1_LR=1e-3) specifically so the already-good pretrained filters were
    nudged gently rather than overwritten. The counts below describe capacity
    (how many numbers exist to be learned), not which stage last touched them.
    """
    total = sum(p.numel() for p in module.parameters())
    trainable = sum(p.numel() for p in module.parameters() if p.requires_grad)
    return total, trainable


def print_parameter_table(model: nn.Module) -> None:
    """Parameter count breakdown by major architectural block.

    MobileNetV3-Small's `features` submodule is a nn.Sequential of 13 blocks:
      features[0]  = the stem (a single 3x3 conv that turns the 3-channel RGB
                     image into 16 initial feature channels, stride 2)
      features[1:-1] = 11 inverted-residual ("bneck") blocks -- MobileNetV3's
                     core building block. Each expands channels with a 1x1
                     conv, filters spatially with a depthwise 3x3 (or 5x5)
                     conv, then projects back down with another 1x1 conv --
                     "inverted" because it's fat in the middle, thin at the
                     ends, the reverse of a classic residual block.
      features[-1] = a final 1x1 conv that expands to a wide feature vector
                     (576 channels) before pooling.
    `avgpool` has no parameters (a fixed spatial-average operation, nothing to
    learn). `classifier` is the two-layer MLP head: Linear(576->1024) ->
    Hardswish -> Dropout -> Linear(1024->3), where only the final Linear was
    randomly initialised for this project (see build_model() docstring).
    """
    print("\n" + "=" * 70)
    print("PART 1b -- PARAMETER COUNT BY BLOCK")
    print("=" * 70)

    total_all, trainable_all = count_parameters(model)

    rows: list[tuple[str, int, int]] = []
    stem_total, stem_trainable = count_parameters(model.features[0])
    rows.append(("stem (features[0])", stem_total, stem_trainable))

    bneck_blocks = model.features[1:-1]
    for i, block in enumerate(bneck_blocks, start=1):
        t, tr = count_parameters(block)
        rows.append((f"inverted-residual block {i:2d}/{len(bneck_blocks)}", t, tr))

    final_conv_total, final_conv_trainable = count_parameters(model.features[-1])
    rows.append(("final 1x1 conv (features[-1])", final_conv_total, final_conv_trainable))

    head_total, head_trainable = count_parameters(model.classifier)
    rows.append(("classifier head (2-layer MLP)", head_total, head_trainable))

    name_w = max(len(r[0]) for r in rows) + 2
    print(f"{'Block':<{name_w}}{'Total params':>14}{'Trainable':>14}")
    print("-" * (name_w + 28))
    for name, t, tr in rows:
        print(f"{name:<{name_w}}{t:>14,}{tr:>14,}")
    print("-" * (name_w + 28))
    print(f"{'TOTAL':<{name_w}}{total_all:>14,}{trainable_all:>14,}")

    # Sanity check: the per-block sum should equal the whole-model total.
    # If it doesn't, our block slicing above missed or double-counted a
    # submodule -- this assertion exists so that error would be loud, not
    # a silently wrong table in the developer's report.
    block_sum = sum(t for _, t, _ in rows)
    assert block_sum == total_all, (
        f"Block breakdown ({block_sum:,}) does not sum to model total "
        f"({total_all:,}) -- block slicing above is wrong.")

    print(f"\n(All {trainable_all:,} parameters are currently 'trainable' in this "
          f"checkpoint because it was saved after stage 2's unfreeze. During "
          f"stage 1, only the classifier head's params -- "
          f"{head_trainable if head_trainable == count_parameters(model.classifier)[1] else '?'} "
          f"of them -- were actually being updated.)")

    print("\n" + "-" * 70)
    print("Size-in-context (for the report -- see plan.md 4.3):")
    print(f"  This model:              {total_all / 1e6:.2f}M parameters")
    print(f"  MobileNetV3-Large:       ~5.4M parameters")
    print(f"  ResNet-50:               ~25M parameters")
    print(f"  MobileNetV3-Small was chosen over both for CPU inference speed at")
    print(f"  demo time (plan.md 4.3) -- the edge loop must sustain >=5 FPS on a")
    print(f"  laptop CPU with no GPU, and a 25M-parameter ResNet-50 would blow")
    print(f"  that budget for a point or two of accuracy this project does not")
    print(f"  need to spend it on.")


# ---------------------------------------------------------------------------
# PART 2 -- Weight health check
# ---------------------------------------------------------------------------

def print_weight_health(model: nn.Module) -> None:
    """Print basic weight statistics for a handful of representative layers.

    WHAT "HEALTHY" LOOKS LIKE, IN GENERAL TERMS:
      - mean near 0, and NOT identically 0 everywhere (all-zero weights would
        mean that layer learned nothing and is passing through no signal)
      - a modest, non-zero std (some spread -- a std of exactly 0 means every
        weight collapsed to the same value, which is also a sign of dead
        training)
      - min/max that are large in magnitude relative to std by only a small
        factor (a few standard deviations) -- a single weight sitting at,
        say, 50 while the rest of the layer sits within +/-0.5 would be an
        extreme outlier, often a symptom of an exploding-gradient problem
      - no NaN or Inf values anywhere -- these indicate the run diverged
        numerically at some point and the checkpoint is not trustworthy
    None of this proves the model is ACCURATE (that's what the confusion
    matrix and recall numbers in eval/confusion_matrix.png are for) -- it only
    checks that training produced ordinary, well-behaved numbers rather than
    a numerically broken checkpoint.
    """
    print("\n" + "=" * 70)
    print("PART 2 -- WEIGHT HEALTH CHECK")
    print("=" * 70)

    layers_to_check: list[tuple[str, torch.Tensor]] = [
        ("stem conv (features[0][0].weight)", model.features[0][0].weight),
        ("middle block 5 depthwise conv (features[5].block[1][0].weight)",
         model.features[5].block[1][0].weight),
        ("middle block 9 depthwise conv (features[9].block[1][0].weight)",
         model.features[9].block[1][0].weight),
        ("final classifier layer (classifier[3].weight)", model.classifier[3].weight),
    ]

    name_w = max(len(n) for n, _ in layers_to_check) + 2
    header = f"{'Layer':<{name_w}}{'mean':>10}{'std':>10}{'min':>10}{'max':>10}  status"
    print(header)
    print("-" * len(header))

    any_abnormal = False
    for name, weight in layers_to_check:
        w = weight.detach()
        mean, std = w.mean().item(), w.std().item()
        w_min, w_max = w.min().item(), w.max().item()
        has_nan_inf = torch.isnan(w).any().item() or torch.isinf(w).any().item()

        # A rough, general-purpose outlier flag: if the tail is more than
        # ~8 standard deviations from the mean, that is unusual for a
        # normally-trained conv/linear layer (weight distributions are
        # typically close to Gaussian/Laplacian and rarely have tails that
        # long). 8 is a deliberately generous threshold -- the goal is to
        # catch genuinely broken layers, not to nitpick ordinary variance.
        outlier_factor = max(abs(w_min - mean), abs(w_max - mean)) / std if std > 0 else float("inf")
        abnormal = has_nan_inf or std == 0.0 or outlier_factor > 8

        status = "OK"
        if has_nan_inf:
            status = "*** NaN/Inf FOUND ***"
        elif std == 0.0:
            status = "*** COLLAPSED (std=0) ***"
        elif outlier_factor > 8:
            status = f"*** OUTLIER (>{outlier_factor:.1f} std) ***"

        any_abnormal = any_abnormal or abnormal
        print(f"{name:<{name_w}}{mean:>10.4f}{std:>10.4f}{w_min:>10.4f}{w_max:>10.4f}  {status}")

    print("-" * len(header))
    if any_abnormal:
        print("\n[FLAG] At least one layer above looks abnormal -- see 'status' column.")
    else:
        print("\nAll checked layers: no NaN/Inf, non-zero spread, no extreme outliers.")
        print("This checkpoint's weights look numerically healthy.")


# ---------------------------------------------------------------------------
# PART 3 -- Feature map visualization
# ---------------------------------------------------------------------------

def load_and_preprocess_image(image_path: Path) -> tuple[torch.Tensor, np.ndarray]:
    """Load one real image and return (model input tensor, displayable RGB array).

    Uses the SAME resize+normalize pipeline as val_tf in train_classifier.py
    (plain 224x224 resize, no augmentation) -- because we want to see what the
    model actually does on a realistic, undistorted input, matching how
    edge/vision.py will feed it frames at deployment.
    """
    img = Image.open(image_path).convert("RGB")
    display_img = np.array(img.resize((224, 224))) / 255.0  # for plotting, 0-1 range

    preprocess = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])
    tensor = preprocess(img).unsqueeze(0)  # add batch dimension: (1, 3, 224, 224)
    return tensor, display_img


def get_activation_maps(model: nn.Module, input_tensor: torch.Tensor
                         ) -> tuple[torch.Tensor, torch.Tensor]:
    """Run one forward pass and capture activations from an early and a late layer.

    A "feature map" is simply the output of one convolutional layer for one
    input image -- a grid of numbers the same width/height as that layer's
    output (smaller than the original image, since MobileNet downsamples
    progressively), with one such grid per output channel. Each channel is a
    learned filter's response map: high values mark WHERE in the image that
    filter's pattern fired strongly.

    We use forward hooks to grab these without modifying the model: a hook is
    a small function PyTorch calls automatically the moment a chosen layer
    finishes computing its output, letting us copy that output out without
    changing anything about how the model runs.

    Early layer (features[1]): still close to the input resolution, and
    research on CNNs (this one included, since it starts from ImageNet
    pretraining) consistently shows early layers respond to low-level visual
    primitives -- edges, colour blobs, simple textures -- not yet anything
    fire/smoke-specific.

    Late layer (features[10]): deep in the network, heavily downsampled, and
    responding to much more abstract, learned combinations of earlier
    features -- by this depth the network has combined many early edge/colour
    detectors into higher-level shape and texture patterns relevant to its
    training task (here, fire/smoke/neutral discrimination).
    """
    activations: dict[str, torch.Tensor] = {}

    def make_hook(key: str):
        def hook(module, hook_input, hook_output):
            activations[key] = hook_output.detach()
        return hook

    early_handle = model.features[1].register_forward_hook(make_hook("early"))
    late_handle = model.features[10].register_forward_hook(make_hook("late"))

    with torch.no_grad():
        model(input_tensor)

    early_handle.remove()
    late_handle.remove()

    # Shape (1, C, H, W) -> (C, H, W): drop the batch dimension, we only ran one image.
    return activations["early"].squeeze(0), activations["late"].squeeze(0)


def save_feature_map_figure(display_img: np.ndarray, early_maps: torch.Tensor,
                             late_maps: torch.Tensor, class_name: str, out_path: Path) -> None:
    """Build and save one figure: original image + a grid of early-layer maps
    + a grid of late-layer maps, for one input image.
    """
    n_show = min(N_CHANNELS_TO_SHOW, early_maps.shape[0], late_maps.shape[0])
    cols = 4
    rows_per_grid = -(-n_show // cols)  # ceiling division

    fig = plt.figure(figsize=(14, 4 + 3.2 * rows_per_grid))
    fig.suptitle(
        f"Feature maps -- {class_name} image\n"
        f"(early layer: features[1], {early_maps.shape[0]} channels, "
        f"{early_maps.shape[1]}x{early_maps.shape[2]} spatial | "
        f"late layer: features[10], {late_maps.shape[0]} channels, "
        f"{late_maps.shape[1]}x{late_maps.shape[2]} spatial)",
        fontsize=11)

    gs_top = fig.add_gridspec(1, 1, top=0.86, bottom=0.68)
    ax_img = fig.add_subplot(gs_top[0])
    ax_img.imshow(display_img)
    ax_img.set_title("Original (224x224 input)")
    ax_img.axis("off")

    def plot_grid(maps: torch.Tensor, title: str, top: float, bottom: float):
        gs = fig.add_gridspec(rows_per_grid, cols, top=top, bottom=bottom, hspace=0.4, wspace=0.15)
        fig.text(0.5, top + 0.02, title, ha="center", fontsize=10, weight="bold")
        # Fixed, reproducible channel sample (not the first N, which for some
        # layers can be visually uninformative near-duplicates) -- seeded once
        # at script start via set_seed(), so re-running is deterministic.
        channel_idxs = sorted(random.sample(range(maps.shape[0]), n_show))
        for i, ch in enumerate(channel_idxs):
            ax = fig.add_subplot(gs[i // cols, i % cols])
            fmap = maps[ch].numpy()
            ax.imshow(fmap, cmap="viridis")
            ax.set_title(f"ch {ch}", fontsize=8)
            ax.axis("off")

    plot_grid(early_maps, "Early layer (edge / colour detectors)", 0.62, 0.36)
    plot_grid(late_maps, "Late layer (higher-level learned features)", 0.32, 0.02)

    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"[saved] {out_path}")


def select_representative_images(class_to_idx: dict[str, int]) -> dict[str, Path]:
    """For each class, pick the val image the model classified correctly with
    the HIGHEST confidence for that class.

    The previous version of this script picked the first image found
    alphabetically in each data/val/<class>/ folder, with no regard for
    whether the model actually got it right -- the fire example this way
    turned out to be a known "confident miss" (predicted neutral, fire
    probability 0.001), the exact wrong image to showcase as "what the
    model learned". This selects the single most confidently-and-correctly
    classified example per class instead -- the clearest, most
    representative "textbook" case, appropriate for a report or viva.

    Reuses val_inference.run_inference (the same helper threshold_sweep.py
    and inspect_misclassified.py already use) rather than writing a second,
    slightly-different inference loop over the val set.
    """
    inference_model, inference_class_to_idx = load_model_for_inference()
    assert inference_class_to_idx == class_to_idx, (
        "val_inference's checkpoint load disagrees with the main model's class "
        "mapping -- both load the same checkpoint file, so this should never happen.")

    probs, labels, paths = run_inference(inference_model, inference_class_to_idx)
    idx_to_class = {i: c for c, i in class_to_idx.items()}
    pred_idx = probs.argmax(axis=1)

    selected: dict[str, Path] = {}
    for class_name in ("fire", "smoke", "neutral"):
        cls_idx = class_to_idx[class_name]
        # Correct predictions only: true label is this class AND the model's
        # argmax prediction is also this class.
        correct_mask = (labels == cls_idx) & (pred_idx == cls_idx)
        if not correct_mask.any():
            print(f"[SKIP] No correctly-classified {class_name} images in the val set "
                  f"-- cannot select a representative example.")
            continue

        # Among correct predictions, the highest confidence (probability) for
        # this class -- the model's most confident, most correct example.
        class_probs = probs[:, cls_idx]
        candidate_indices = np.where(correct_mask)[0]
        best_idx = candidate_indices[np.argmax(class_probs[candidate_indices])]

        selected[class_name] = paths[best_idx]
        prob_breakdown = ", ".join(
            f"{idx_to_class[i]}={probs[best_idx, i]:.3f}" for i in range(probs.shape[1]))
        print(f"{class_name}: selected {paths[best_idx]}")
        print(f"  correctly predicted {class_name} (probs: {prob_breakdown})")

    return selected


def run_feature_map_visualization(model: nn.Module, selected_images: dict[str, Path]) -> None:
    print("\n" + "=" * 70)
    print("PART 3 -- FEATURE MAP VISUALIZATION")
    print("=" * 70)
    print("A feature map is one convolution filter's response across the whole")
    print("image -- bright regions are where that filter's learned pattern fired.")
    print("Early layers fire on low-level primitives (edges, colour contrast);")
    print("late layers fire on abstract, task-specific combinations of those.\n")

    for class_name, image_path in selected_images.items():
        input_tensor, display_img = load_and_preprocess_image(image_path)
        early_maps, late_maps = get_activation_maps(model, input_tensor)

        out_path = MODEL_UNDERSTANDING_DIR / f"feature_maps_{class_name}.png"
        save_feature_map_figure(display_img, early_maps, late_maps, class_name, out_path)


# ---------------------------------------------------------------------------
# PART 4 -- Simplified architecture diagram
# ---------------------------------------------------------------------------

def draw_architecture_diagram(model: nn.Module, out_path: Path) -> None:
    """Draw a simplified stem -> blocks -> head -> output block diagram.

    Deliberately NOT a torchviz computation graph -- those render every
    individual tensor op (add, reshape, batchnorm, etc.) as a separate node
    and for a network this deep become a dense, unreadable wall of boxes.
    This is a hand-summarized version instead: one box per architecturally
    meaningful stage, annotated with the spatial resolution and parameter
    count at that stage, which is what's actually useful to point at in a
    report or explain out loud in a viva.
    """
    stem_total, _ = count_parameters(model.features[0])
    bneck_blocks = model.features[1:-1]
    bneck_total, _ = count_parameters(bneck_blocks)
    final_conv_total, _ = count_parameters(model.features[-1])
    head_total, _ = count_parameters(model.classifier)
    grand_total, _ = count_parameters(model)

    # (label, sublabel, param_count_str, spatial_dim_str)
    stages = [
        ("Input", "RGB image", "-", "224x224x3"),
        ("Stem", "1 conv, stride 2", f"{stem_total:,} params", "112x112x16"),
        ("Inverted-residual\nblocks", f"{len(bneck_blocks)} bneck blocks", f"{bneck_total:,} params", "7x7x96"),
        ("Final 1x1 conv", "channel expansion", f"{final_conv_total:,} params", "7x7x576"),
        ("Global avg pool", "spatial -> vector", "0 params", "1x1x576"),
        ("Classifier head", "Linear-Hardswish-Dropout-Linear", f"{head_total:,} params", "3 logits"),
        ("Output", "softmax", "-", "neutral / smoke / fire"),
    ]

    fig, ax = plt.subplots(figsize=(16, 4))
    ax.set_xlim(0, len(stages))
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_title(
        f"FireWatch classifier -- MobileNetV3-Small, {grand_total / 1e6:.2f}M total parameters\n"
        f"(simplified summary diagram -- not a full computation graph)",
        fontsize=12)

    box_w, box_h, gap = 0.82, 0.5, 0.18
    colors = ["#dbe4f0", "#f0d9b5", "#c9e4c5", "#c9e4c5", "#f5e6a8", "#f0b8b8", "#dbe4f0"]

    for i, (label, sublabel, params, spatial) in enumerate(stages):
        x = i + (1 - box_w) / 2
        y = 0.5 - box_h / 2
        box = patches.FancyBboxPatch(
            (x, y), box_w, box_h,
            boxstyle="round,pad=0.02", linewidth=1.2,
            edgecolor="black", facecolor=colors[i % len(colors)])
        ax.add_patch(box)
        ax.text(i + 0.5, y + box_h * 0.68, label, ha="center", va="center", fontsize=9.5, weight="bold")
        ax.text(i + 0.5, y + box_h * 0.40, sublabel, ha="center", va="center", fontsize=7.5, style="italic")
        ax.text(i + 0.5, y - 0.10, spatial, ha="center", va="top", fontsize=8, color="#333333")
        ax.text(i + 0.5, y - 0.20, params, ha="center", va="top", fontsize=8, color="#555555")

        if i < len(stages) - 1:
            ax.annotate("", xy=(i + 1 + (1 - box_w) / 2 - 0.02, 0.5),
                        xytext=(x + box_w + 0.02, 0.5),
                        arrowprops=dict(arrowstyle="->", lw=1.4))

    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"[saved] {out_path}")


# ---------------------------------------------------------------------------
# PART 5 -- Grad-CAM (explainability: WHERE the model is looking)
# ---------------------------------------------------------------------------
#
# WHAT GRAD-CAM ACTUALLY SHOWS, IN PLAIN LANGUAGE:
# Feature maps (Part 3) show what individual filters respond to in general.
# Grad-CAM answers a narrower, more useful question for a report or viva:
# for THIS specific image and THIS specific prediction, which pixel regions
# most influenced the model's decision? It does this by asking "if I nudged
# each spatial location in the last conv layer up or down, how much would
# that change the model's score for the predicted class" (the gradient of
# the predicted class's output score with respect to that layer) and using
# the answer to weight each channel's feature map, then summing them into
# one heatmap the same spatial size as the last conv layer, upsampled back
# to the original image. Warm colours (the overlay below) mark regions the
# model leaned on heavily to make this decision; cool/dark regions mark
# regions it effectively ignored. This is the standard evidence used to
# verify a vision model is looking at the actually-relevant region (e.g. the
# flame or smoke plume itself) rather than an unrelated part of the image
# (background clutter, lighting artifacts, a watermark, the sky) -- a model
# that gets the right answer for the wrong reason is a real risk in a
# life-safety system and would not be visible from accuracy numbers alone.


def generate_gradcam(model: nn.Module, input_tensor: torch.Tensor,
                      target_class_idx: int) -> np.ndarray:
    """Standard Grad-CAM: hook the last conv layer's activations and gradients.

    Target layer: model.features[-1], the final 1x1 conv (576 channels,
    7x7 spatial) -- the last layer before global average pooling, and the
    conventional Grad-CAM target for a CNN classifier since it is the
    deepest layer that still retains spatial location information (the
    classifier head that follows has none).

    Steps (the standard Grad-CAM method):
      1. Forward hook captures that layer's output activations, A (shape
         C x H x W).
      2. Full backward hook captures the gradient of the predicted class's
         score with respect to A, dScore/dA (same shape).
      3. Global-average-pool the gradients over H,W to get one importance
         weight per channel, alpha_c -- "on average, how much does channel c
         matter to this prediction".
      4. Weighted sum of the activations by alpha_c, then ReLU (Grad-CAM only
         keeps pixels with a POSITIVE influence on the target class -- a
         negative contribution means that region pushed the score down, not
         up, which isn't "why the model chose this class").
      5. Upsample the resulting H x W heatmap to the input image's 224x224
         and normalize to [0, 1] for display.
    """
    activations: dict[str, torch.Tensor] = {}
    gradients: dict[str, torch.Tensor] = {}

    def forward_hook(module, hook_input, hook_output):
        activations["value"] = hook_output

    def backward_hook(module, grad_input, grad_output):
        gradients["value"] = grad_output[0]

    target_layer = model.features[-1]
    fwd_handle = target_layer.register_forward_hook(forward_hook)
    bwd_handle = target_layer.register_full_backward_hook(backward_hook)

    model.zero_grad()
    logits = model(input_tensor)
    score = logits[0, target_class_idx]
    score.backward()

    fwd_handle.remove()
    bwd_handle.remove()

    act = activations["value"].squeeze(0)   # (C, H, W)
    grad = gradients["value"].squeeze(0)    # (C, H, W)

    alpha = grad.mean(dim=(1, 2))           # (C,) -- per-channel importance
    cam = torch.relu((alpha[:, None, None] * act).sum(dim=0))  # (H, W)

    cam = cam.unsqueeze(0).unsqueeze(0)     # (1, 1, H, W) for interpolate
    cam = F.interpolate(cam, size=(224, 224), mode="bilinear", align_corners=False)
    cam = cam.squeeze().detach().numpy()

    cam_min, cam_max = cam.min(), cam.max()
    if cam_max > cam_min:
        cam = (cam - cam_min) / (cam_max - cam_min)
    else:
        cam = np.zeros_like(cam)  # degenerate case: model gave this class zero gradient everywhere
    return cam


def save_gradcam_overlay(display_img: np.ndarray, cam: np.ndarray, class_name: str,
                          predicted_class: str, out_path: Path) -> None:
    """Save the original image with a semi-transparent heatmap overlay.

    Not the heatmap alone -- overlaying it on the real image is what lets a
    reader immediately see WHICH object or region it corresponds to (e.g.
    "yes, that's the flame") rather than an abstract blob in isolation.
    """
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.imshow(display_img)
    ax.imshow(cam, cmap="jet", alpha=0.45)  # warm colours = high influence on the decision
    ax.set_title(f"Grad-CAM -- {class_name} image\n(predicted: {predicted_class})", fontsize=10)
    ax.axis("off")
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"[saved] {out_path}")


def run_gradcam(model: nn.Module, selected_images: dict[str, Path],
                 class_to_idx: dict[str, int]) -> None:
    print("\n" + "=" * 70)
    print("PART 5 -- GRAD-CAM (WHERE the model is looking)")
    print("=" * 70)
    print("Heatmap overlay on the original image -- warm colours mark pixel")
    print("regions that most influenced the model's decision for its predicted")
    print("class. See the module-level comment above for the full explanation.\n")

    idx_to_class = {i: c for c, i in class_to_idx.items()}

    for class_name, image_path in selected_images.items():
        input_tensor, display_img = load_and_preprocess_image(image_path)

        with torch.no_grad():
            logits = model(input_tensor)
            pred_idx = int(logits.argmax(dim=1))
        predicted_class = idx_to_class[pred_idx]

        # Grad-CAM w.r.t. the model's own predicted class -- "why did it say
        # this", the standard Grad-CAM framing. Since these images were
        # selected as correctly-classified (select_representative_images),
        # predicted_class == class_name here.
        cam = generate_gradcam(model, input_tensor, pred_idx)

        out_path = MODEL_UNDERSTANDING_DIR / f"gradcam_{class_name}.png"
        save_gradcam_overlay(display_img, cam, class_name, predicted_class, out_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    set_seed(SEED)

    if not CHECKPOINT_PATH.exists():
        print(f"[ERROR] Checkpoint not found: {CHECKPOINT_PATH}")
        print("This script only inspects an already-trained model -- it does not train one.")
        return

    model, class_to_idx = load_model(CHECKPOINT_PATH)

    MODEL_UNDERSTANDING_DIR.mkdir(parents=True, exist_ok=True)

    print_and_save_architecture(model, MODEL_UNDERSTANDING_DIR / "architecture.txt")
    print_parameter_table(model)
    print_weight_health(model)

    selected_images = select_representative_images(class_to_idx)
    run_feature_map_visualization(model, selected_images)

    print("\n" + "=" * 70)
    print("PART 4 -- SIMPLIFIED ARCHITECTURE DIAGRAM")
    print("=" * 70)
    draw_architecture_diagram(model, MODEL_UNDERSTANDING_DIR / "architecture_diagram.png")

    run_gradcam(model, selected_images, class_to_idx)

    print("\n" + "=" * 70)
    print("DONE -- output files:")
    for fname in ("architecture.txt", "architecture_diagram.png",
                  "feature_maps_fire.png", "feature_maps_smoke.png", "feature_maps_neutral.png",
                  "gradcam_fire.png", "gradcam_smoke.png", "gradcam_neutral.png"):
        path = MODEL_UNDERSTANDING_DIR / fname
        status = "OK" if path.exists() else "MISSING"
        print(f"  [{status}] {path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
