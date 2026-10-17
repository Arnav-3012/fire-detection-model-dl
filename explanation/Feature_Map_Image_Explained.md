# What This Image Actually Shows — Feature Maps at Two Depths of MobileNetV3-Small

Reference image: `1788704483956_image.png` — "Feature maps -- fire image", early layer `features[1]` (16 channels, 56x56 spatial) vs. late layer `features[10]` (96 channels, 7x7 spatial).

Prerequisites: "Convolutional Neural Networks - From First Principles to Full Depth" and "MobileNetV3-Small - Bridging Plain CNNs to FireWatch's Production Model".

---

## 0. What Kind of Visualization This Is

This is a **feature map dump**, not Grad-CAM and not an SE-gate readout (see the separate interpretability document for those). It is the simplest possible way to look inside a network: run one real image forward through the model, stop at a chosen layer, and plot every channel's raw output as a grayscale/color grid. No gradients, no backward pass, no weighting by importance — just "what number sat in this position, in this channel, after this layer processed the image." That simplicity is also its limitation: it shows you *what the layer computed*, never *whether the final decision cared about it*.

The original photo (top) is a real, dramatic fire scene — two figures in silhouette, a bright orange flame plume rising between them, a dark, low-light industrial background. This is exactly the kind of image the model's very first layers get to see.

---

## 1. The Early Layer — `features[1]`, 16 Channels, 56x56

### 1.1 Why 56x56, Not 224x224

The input image is 224x224x3 (CNN doc, Section 4; MobileNetV3 doc, Section 8's forward-pass trace). `features[1]` sits after the network's very first standard convolution (stride 2, MobileNetV3 doc Section 8: 224 -> 112) and the first bottleneck block (another stride-2 step: 112 -> 56). Two halvings, 224 -> 112 -> 56, using the exact output-size formula from the CNN guide (`O = (N - F + 2P) / S + 1`). Nothing mysterious about the 56 — it is arithmetic, not a design choice made specifically for this visualization.

### 1.2 Why All 12 Shown Channels Look Almost Identical

Look at channels 0, 1, 2, 3, 4, 8, 10, 11, 12, 13, 14, 15 in the image — every single one shows the same faint outline: two human silhouettes and a bright, branching flame shape in the middle, just rendered in different background colors (yellow-green vs. blue-purple) and with slightly different contrast on the edges.

This is expected, and it is the single most important thing to take from the top half of this image: **this early in the network, channels have not yet specialized.** Recall from the CNN guide (Section 2.3) that filters start as random noise and specialize only gradually, layer by layer, as training proceeds. The very first layers of any CNN — including a fully-trained, production MobileNetV3-Small — tend to converge into general-purpose edge and color-contrast detectors, because those are the most broadly useful patterns for almost any downstream task. An edge detector fires on ANY sharp light-to-dark transition, whether that edge belongs to a person's shoulder, a flame's silhouette, or a background pipe. That is exactly why channel 0 and channel 12 both trace the same outline of the scene — they are both, in effect, running some version of "where is there a sharp brightness change," just with slightly different sensitivity or sign.

The receptive field at this depth is still small (CNN guide, Section 7 — only a couple of stacked 3x3-equivalent operations deep), so each channel is only "seeing" a small local patch of the image at a time, which is also why the outlines look thin and wiry rather than solid regions.

### 1.3 Reading the Color Differences

The color scale (a "viridis"-style colormap: dark blue/purple = low activation value, yellow-green = high activation value) is doing real work here. Channels like 1, 10, 12 lean heavily blue/purple almost everywhere except right along the silhouette edges — meaning most of the image produced a low, near-zero response, with the edges producing a sharp positive spike. Channels like 0, 4, 15 lean more yellow-green across large areas — a generally higher baseline activation, with the edges still visible as darker or more saturated lines cutting through. Both patterns are consistent with an edge/contrast detector; the difference is really just which polarity and background sensitivity that particular random-initialized-then-trained filter settled into.

---

## 2. The Late Layer — `features[10]`, 96 Channels, 7x7

### 2.1 Why 7x7 and Why 96 Channels

By `features[10]`, the image has passed through most of MobileNetV3-Small's bottleneck blocks (MobileNetV3 doc, Section 7.2's full architecture table). Repeated stride-2 downsampling collapses the spatial size all the way down: 224 -> 112 -> 56 -> 28 -> 14 -> 7. The channel count, meanwhile, has gone the opposite direction — up to 96 — because each bottleneck block's expand/project structure (MobileNetV3 doc, Section 3) increases representational capacity even as spatial detail is discarded. This is the general CNN pattern the guide's Section 7 introduced: as you go deeper, you trade spatial resolution for a richer, higher-level description of what is present.

### 2.2 Why These 12 Channels Look Genuinely Different From Each Other

This is the real story of the bottom half of the image. Compare channel 3 (a scattered, mostly mid-tone grid with one sharp dark cell near the top) against channel 29 (a busy, high-contrast checkerboard of dark and bright cells across almost the whole 7x7 grid) against channel 89 (mostly uniform mid-green with two or three isolated bright yellow cells). These are not the same underlying pattern rendered in different colors — they are structurally different response maps. That is exactly what the CNN guide's Section 7 (receptive field growth) and Section 13.3 (what filters learn) predicted would happen by this depth: each channel's receptive field is now large enough, and the network has gone through enough non-linear activations (CNN guide, Section 5) and squeeze-and-excite re-weighting (MobileNetV3 doc, Section 4) in between, that channels have specialized into detecting distinct, more abstract combinations of shape, texture, and color rather than a shared generic edge.

Concretely, for a fire/smoke/neutral classifier, this is the depth at which you would expect to find (though this single visualization alone cannot prove which channel is which) some channels responding preferentially to the flame's specific orange/yellow color-and-texture combination, others to the darker silhouette regions, and others to the background industrial structure — each pattern occupying a different, specific subset of the 7x7 grid rather than all of them tracing the same outline the way the early-layer channels did.

### 2.3 Why the Grid Looks "Blocky" Now

At 7x7, each cell in the plot corresponds to a fairly large patch of the original 224x224 image (each cell's receptive field spans a wide swath of pixels, per the CNN guide's Section 7 formula). This is why the late-layer plots look like coarse, blocky mosaics rather than the thin, wiry outlines seen in the early layer — spatial precision has been deliberately traded away for semantic richness. You cannot point to one 7x7 cell and say "that's the flame's exact left edge" the way you almost could at 56x56 — you can only say "this general region of the image."

---

## 3. What This Image Does and Does Not Prove

**It shows:** a real, measured, non-simulated snapshot of what two specific layers of the actual trained model computed for this actual fire photo. The early/late contrast (shared generic outlines vs. specialized distinct patterns) is genuine evidence that the network is doing what the CNN guide's theory predicts — building up from simple, shared features to specialized, abstract ones.

**It does not show:** which of these channels the final fire/smoke/neutral decision actually relied on. A channel lighting up brightly here (say, channel 29) could still be irrelevant to the final prediction if later layers do not weight it heavily, or if the squeeze-and-excite gate for that channel (MobileNetV3 doc, Section 4.3) suppresses it before it reaches the classifier head. It also does not show *where in the original image* a given late-layer channel's activation actually maps back to, in the fine-grained, upsampled way Grad-CAM does.

For the "which feature/channel actually mattered for this prediction" question, that is what the Grad-CAM and squeeze-and-excite gate readout methods in the companion interpretability document are for — this image is the right first step (confirming the network's internal representations look sensible and increasingly specialized), not the last one.

---

## 4. Quick Reference

| | Early layer (`features[1]`) | Late layer (`features[10]`) |
|---|---|---|
| Spatial size | 56x56 | 7x7 |
| Channels | 16 | 96 |
| What channels look like | Nearly identical to each other | Distinct from each other |
| What they detect | Generic edges / color contrast | Specialized, higher-level patterns |
| Receptive field | Small | Large |
| Precision of "where" | High (thin outlines visible) | Low (coarse, blocky regions) |
| Can tell you what mattered for the final decision? | No | No — needs Grad-CAM / SE gates |
