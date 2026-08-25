"""Evaluation reporting for the FireWatch classifier: metrics, confusion matrix, curves.

Split out of train_classifier.py (same pattern as data_report.py in Phase 1)
to keep each file near info.md 3.3's ~200-line guideline.

Everything here is computed from a single confusion matrix rather than
sklearn, deliberately: the arithmetic IS the lesson. Precision, recall and
F1 are just ratios of confusion-matrix cells, and seeing them derived by
hand makes it obvious what each one actually measures.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless backend -- we only save files, never open windows
import matplotlib.pyplot as plt
import numpy as np


def confusion_matrix(true_labels: np.ndarray, pred_labels: np.ndarray, n_classes: int) -> np.ndarray:
    """Build an n x n confusion matrix: rows = true class, columns = predicted class.

    cm[i, j] counts images whose TRUE class is i but which the model PREDICTED
    as j. The diagonal is everything the model got right; every off-diagonal
    cell is a specific kind of mistake (e.g. cm[fire, neutral] = real fires the
    model called "nothing to see here" -- the single worst cell in this project).
    """
    cm = np.zeros((n_classes, n_classes), dtype=np.int64)
    for t, p in zip(true_labels, pred_labels):
        cm[t, p] += 1
    return cm


def per_class_metrics(cm: np.ndarray) -> dict[int, dict[str, float]]:
    """Compute precision, recall and F1 for each class from the confusion matrix.

    In plain language, for one class (say fire):
    - PRECISION = of everything the model CALLED fire, what fraction really was
      fire? Low precision = false alarms (crying wolf erodes trust).
    - RECALL    = of everything that really WAS fire, what fraction did the
      model catch? Low recall = missed fires. For this project recall on the
      fire class outranks every other number (info.md 4.1): a false alarm is
      annoying, a missed real fire defeats the entire purpose of the system.
    - F1 = harmonic mean of the two. The harmonic (not arithmetic) mean punishes
      imbalance: a model with 1.0 precision but 0.1 recall gets F1 0.18, not
      0.55 -- so F1 only looks good when BOTH are good.
    """
    metrics: dict[int, dict[str, float]] = {}
    for i in range(cm.shape[0]):
        tp = cm[i, i]  # true class i, predicted i -- correct hits
        # Column sum minus tp = other classes the model mislabelled AS class i.
        fp = cm[:, i].sum() - tp
        # Row sum minus tp = real class-i images the model missed.
        fn = cm[i, :].sum() - tp
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        metrics[i] = {"precision": precision, "recall": recall, "f1": f1}
    return metrics


def print_metrics_table(metrics: dict[int, dict[str, float]], idx_to_class: dict[int, str]) -> None:
    """Print the per-class metrics table plus macro F1 (info.md 4.1 requires all of these)."""
    print("\n=== Per-class metrics (best checkpoint) ===")
    print(f"{'Class':<10}{'Precision':>11}{'Recall':>9}{'F1':>7}")
    for idx in sorted(metrics):
        m = metrics[idx]
        print(f"{idx_to_class[idx]:<10}{m['precision']:>11.4f}{m['recall']:>9.4f}{m['f1']:>7.4f}")
    # Macro F1 averages the per-class F1s with EQUAL weight per class, so a weak
    # minority class drags it down even if the majority class hides it in
    # overall accuracy -- exactly why info.md 4.1 tracks it against imbalance.
    macro_f1 = float(np.mean([m["f1"] for m in metrics.values()]))
    print(f"{'macro F1':<10}{'':>11}{'':>9}{macro_f1:>7.4f}")


def save_confusion_matrix_plot(cm: np.ndarray, idx_to_class: dict[int, str], out_path: Path) -> None:
    """Render the confusion matrix as an annotated heatmap image."""
    n = cm.shape[0]
    labels = [idx_to_class[i] for i in range(n)]
    fig, ax = plt.subplots(figsize=(5, 4.5))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(n), labels)
    ax.set_yticks(range(n), labels)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title("Confusion matrix (val, best checkpoint)")
    # Annotate every cell with its count; flip text colour on dark cells.
    threshold = cm.max() / 2 if cm.max() > 0 else 0
    for i in range(n):
        for j in range(n):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center",
                    color="white" if cm[i, j] > threshold else "black")
    fig.colorbar(im)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def save_training_curves(history: dict[str, list[float]], out_path: Path) -> None:
    """Plot train/val loss and accuracy per epoch, side by side.

    These curves are the primary overfitting diagnostic: train loss falling
    while val loss rises means the model is memorising the training set
    rather than learning generalisable features.
    """
    epochs = range(1, len(history["train_loss"]) + 1)
    fig, (ax_loss, ax_acc) = plt.subplots(1, 2, figsize=(11, 4.5))

    ax_loss.plot(epochs, history["train_loss"], label="train")
    ax_loss.plot(epochs, history["val_loss"], label="val")
    ax_loss.set_xlabel("Epoch")
    ax_loss.set_ylabel("Cross-entropy loss")
    ax_loss.set_title("Loss")
    ax_loss.legend()

    ax_acc.plot(epochs, history["train_acc"], label="train")
    ax_acc.plot(epochs, history["val_acc"], label="val")
    ax_acc.set_xlabel("Epoch")
    ax_acc.set_ylabel("Accuracy")
    ax_acc.set_title("Accuracy")
    ax_acc.legend()

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
