# Seeing Inside the Model — Feature Maps, Grad-CAM, and Feature Importance

Prerequisites: "Convolutional Neural Networks - From First Principles to Full Depth", "MobileNetV3-Small - Bridging Plain CNNs to FireWatch's Production Model", and "Data In, Predictions Out". This document assumes all three.

Reference image: `1788704271400_image.png` (feature map visualization on a real fire image, `features[1]` vs `features[10]`).

---

## 0. Two Different Questions, Two Different Tools

"Which feature mattered most" is not a single-list question for a CNN the way it is for a tree model like XGBoost (`feature_importances_`). A CNN's "features" are the numbers inside 2.5 million filter weights spread across many blocks — none of them map cleanly onto a human label like "orange color" or "flicker pattern." The question actually splits into two different, separately-answerable questions:

- **Where in the image did the model look?** → Grad-CAM
- **Which channels did the model itself decide to boost or suppress?** → the Squeeze-and-Excite (SE) gate values already computed inside the trained network (MobileNetV3 doc, Section 4)

Neither gives a single ranked list the way a tabular model does. That is the honest shape of what a CNN can tell you, not a soft-pedaled limitation.

---

## 1. What the Reference Image Actually Shows

The uploaded image is a **feature map visualization** — a simpler, different technique from Grad-CAM. It asks "what does the output of a specific layer look like, for this specific image?" No gradients, no backprop — just running the image forward and stopping partway through to look at what is there.

**Top row — early layer (`features[1]`, 16 channels, 56x56 spatial size).** At this depth MobileNetV3-Small has barely processed the image — this is only the second layer. Every one of the 12 shown channels looks almost identical: a faint ghost-outline of the two people and the flame, with slightly different color intensities. This is expected: early layers have not yet specialized — they behave like generic edge/color detectors, so they all roughly trace the same silhouette.

**Bottom row — late layer (`features[10]`, 96 channels, 7x7 spatial size).** By this depth the image has passed through most of the bottleneck blocks (MobileNetV3 doc, Section 7's architecture table — `features[10]` sits around the 7x7x96 stage). Two things changed: spatial resolution collapsed from 56x56 to 7x7 (stride-2 downsampling accumulating through the bottleneck blocks), and the 12 shown channels now look genuinely *different from each other* rather than variations on one shared outline — channel 29 lights up in a completely different pattern than channel 89. This is the visual proof that, by this depth, each channel has specialized to respond to a specific, more abstract pattern rather than a generic edge (CNN doc, Section 7's receptive-field growth, made concrete).

**What this image cannot tell you:** it does not say *why* those channels lit up that way, and it does not say which channel mattered most for the final "fire" prediction — a channel can light up brightly and still be irrelevant to the final decision if the layers after it do not weight it heavily. That gap is exactly why Grad-CAM exists as a separate, complementary technique.

---

## 2. Grad-CAM — Full Math From Scratch

### 2.1 The Setup

Take the last convolutional feature map before global average pooling — for MobileNetV3-Small this is the 7x7x576 feature map from the MobileNetV3 doc's Section 7.2 (the layer immediately before pooling). Call it `A`, with `K = 576` channels, each channel `k` being a 7x7 grid `A^k`.

### 2.2 Step 1 — Gradient of the Class Score With Respect to Every Feature Map Pixel

Let `y^c` be the raw logit (pre-softmax score, CNN doc Section 5.6) for class `c` — say, "fire." Compute:

```
∂y^c / ∂A^k_ij
```

This is the same partial-derivative machinery from the CNN doc's backpropagation section (Section 11), just stopped partway through the network instead of running all the way back to the input pixels. It answers: if this one number in this one channel's feature map went up slightly, how much would the fire score change?

### 2.3 Step 2 — Average Gradients Over Space to Get One Importance Weight Per Channel

This is the actual "weight given to a feature map" — and it has a name, `alpha_k^c`:

```
alpha_k^c = (1 / (7 x 7)) x sum over i,j of (∂y^c / ∂A^k_ij)
```

This is a global average pool (CNN doc, Section 6) applied to the *gradients* instead of the activations. A large positive `alpha_k^c` means "increasing this channel, on average across its whole 7x7 map, increases the fire score" — this channel matters, and matters positively, for this specific prediction.

**Worked example.** Suppose channel 29 (from the reference image) has these 4 gradient values in a toy 2x2 simplification (real is 7x7, kept small here so the arithmetic is visible): `[0.8, 0.6, 0.4, 0.2]`.

```
alpha_29^fire = (0.8 + 0.6 + 0.4 + 0.2) / 4 = 2.0 / 4 = 0.5
```

Compare channel 3, with gradients `[-0.1, 0.05, -0.2, 0.05]`:

```
alpha_3^fire = (-0.1 + 0.05 - 0.2 + 0.05) / 4 = -0.2 / 4 = -0.05
```

Channel 29 clearly matters more, and positively, for "fire" than channel 3 does — for this specific image. This is a per-image, per-class number, not a fixed global property of the channel.

### 2.4 Step 3 — Weighted Combination, Then Keep Only Positive Evidence

```
L^c_GradCAM = ReLU( sum over k of (alpha_k^c x A^k) )
```

This is a weighted sum across all 576 channels — the same weighted-sum-then-activation pattern as a dense layer (CNN doc, Section 9), applied across channels instead of neurons. The ReLU (CNN doc, Section 5.4) discards anything that would have *decreased* the fire score, keeping only evidence *for* fire.

### 2.5 Step 4 — Upsample to the Original Image Size

`L^c_GradCAM` is still 7x7 — the same spatial size as the last conv layer. It gets resized up to 224x224 (the CNN doc's output-size math, run in reverse) and overlaid as a heatmap on the original photo — this produces the familiar red/yellow "where the model looked" visualization.

### 2.6 Minimal Code Sketch

```python
import torch

activations = {}
gradients = {}

def forward_hook(module, input, output):
    activations['value'] = output

def backward_hook(module, grad_input, grad_output):
    gradients['value'] = grad_output[0]

target_layer = model.features[-1]  # last conv block before pooling
target_layer.register_forward_hook(forward_hook)
target_layer.register_full_backward_hook(backward_hook)

output = model(image_tensor)         # forward pass
fire_score = output[0, 0]            # index 0 = fire (Data doc, Section 5.1)
fire_score.backward()                # populates gradients['value']

A = activations['value'][0]          # shape [576, 7, 7]
grads = gradients['value'][0]        # shape [576, 7, 7]

alpha = grads.mean(dim=(1, 2))       # global average pool of gradients -> [576]
weighted = (alpha.view(-1, 1, 1) * A).sum(dim=0)  # weighted sum across channels -> [7, 7]
heatmap = torch.relu(weighted)       # keep only positive evidence
heatmap = torch.nn.functional.interpolate(
    heatmap.unsqueeze(0).unsqueeze(0), size=(224, 224), mode='bilinear'
)[0, 0]
```

---

## 3. Reading Out the Squeeze-and-Excite Gate — the Model's Own Importance Number

Unlike Grad-CAM (computed after training, from outside), the SE gate value is something MobileNetV3-Small computes for itself, live, on every forward pass (MobileNetV3 doc, Section 4.3). It is a real number between 0 and 1 per channel, and it can be read out directly.

```python
activations = {}

def hook(module, input, output):
    activations['se_gate'] = output  # per-channel 0-1 weights

model.features[10].block[2].se_layer.register_forward_hook(hook)
model(one_image_tensor)
print(activations['se_gate'])  # e.g. tensor([0.91, 0.08, 0.63, ...]) - one value per channel
```

This is a genuinely different signal from Grad-CAM's `alpha_k^c`: the SE gate is the network's own internal "how much do I trust this channel right now" decision, learned during training; Grad-CAM's weight is an external, after-the-fact measurement of "how much did this channel actually sway the fire score." In practice the two often broadly agree (a channel the SE block boosted heavily tends to also get a high Grad-CAM weight), but they are not the same computation and can disagree.

---

## 4. Combining Both — What "Why Did the Model Say Fire" Actually Looks Like

For one real image: Grad-CAM produces a heatmap glowing over the actual flame region (not the person's helmet, not the background sky) — spatial evidence. Reading the SE gate values for that same forward pass gives a numeric list like channel 29 = 0.91, channel 3 = 0.12 — channel-level evidence. If both agree — the high-Grad-CAM-weight channels are also the high-SE-gate channels, and the heatmap sits on the flame — that is about as strong an honest answer as "how do we know" gets for a CNN.

---

## 5. Checking or Modifying Weights — What Is Actually Safe

Directly hand-editing filter numbers is not a real workflow here — with 2.5 million parameters spread across many-channel bottleneck blocks, there is no meaningful "change this one weight" edit a human would perform. What is real, and already part of this project:

- **Inspecting** a weight tensor's shape and values:
  ```python
  print(model.state_dict()['features.10.block.1.0.weight'].shape)
  print(model.state_dict()['features.10.block.1.0.weight'].data)
  ```
  Useful for sanity-checking (confirming a layer's shape matches the architecture table), not for tuning.

- **Changing** what a weight becomes: always through retraining (CNN doc, Section 13.2's training loop), never hand-editing.

- **Validating any change** — a new checkpoint, a new augmentation setting, a new hard-negative batch — the same way v3-to-v4 was validated in the project's own report:
  1. Re-run `eval/threshold_sweep.py` and `eval/smoke_threshold_sweep.py`; compare recall/precision against the *previous* checkpoint (Data doc, Section 9's TP/FP math).
  2. Re-run the fixed adversarial clips (sunset, steam, TV-fire, candle) — a regression here matters even if raw accuracy improved.
  3. Re-check ONNX/PyTorch numerical equivalence (MobileNetV3 doc, Section 9.5) before promoting a new checkpoint to production.
  4. Re-run `train/check_leakage.py` if the dataset changed at all.

No single "importance list" exists for a CNN — but Grad-CAM (spatial evidence) and SE gates (channel-level evidence) together are the real, defensible tools, and weight changes only ever happen through retraining plus this exact regression checklist, never hand-editing.

---

## 6. Quick Reference

| Question | Tool | What it produces |
|---|---|---|
| Where did the model look in this image? | Grad-CAM | A 224x224 heatmap overlaid on the photo |
| Which channels did the model itself trust most? | SE gate readout | A 0-to-1 number per channel, per forward pass |
| Is a channel's importance fixed across all images? | Neither — both are per-image, per-class | N/A |
| How do I change a weight? | Retrain, never hand-edit | A new checkpoint |
| How do I know a retrained model is still good? | threshold_sweep.py, smoke_threshold_sweep.py, adversarial clips, ONNX equivalence, check_leakage.py | Recall/precision comparison against the previous checkpoint |

**Formulas:**

```
alpha_k^c = (1 / (H x W)) x sum over i,j of (∂y^c / ∂A^k_ij)
L^c_GradCAM = ReLU( sum over k of (alpha_k^c x A^k) )
```
