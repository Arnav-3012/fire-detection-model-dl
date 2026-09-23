"""Video capture for FireWatch edge loop.

Camera handling only — no model or inference logic belongs here (info.md 3.4).
"""

import sys

import cv2
import numpy as np

DEVICE_INDEX = 0  # MacBook built-in camera, confirmed working via scripts/test_camera.py (Phase 0f)


class Camera:
    """Wraps cv2.VideoCapture for the edge loop's single video source.

    A thin wrapper rather than using cv2.VideoCapture directly so main.py and
    vision.py depend on a stable interface (read/encode_jpeg/release) instead
    of OpenCV's API, and so the "camera failed to open" failure mode has one
    place to be handled loudly, per info.md 3.2's failure table (camera
    failures are loud and exit, not silently retried).

    `source` accepts either the webcam device index (default, unchanged) or
    an MJPEG stream URL (e.g. "http://<esp32-ip>/stream") — cv2.VideoCapture
    natively opens both the same way (FFmpeg backend for URLs), so this is
    a togglable capture source, not a separate code path (phase13a-2). Model
    loading, preprocessing, TemporalVoter, and thresholds in vision.py are
    untouched by this — only where frames come from changes.

    ESP32-CAM color-cast correction (2026-09-17): the GC2145 sensor on the
    ESP32-CAM board produces frames with a strong, consistent red bias
    (measured on a saved frame: R/G=1.98, R/B=2.44 channel means) that
    hurt fire-detection confidence relative to the webcam on identical
    footage. Ruled out at the firmware level first (Level 2 research into
    espressif/esp32-camera's gc2145.c and to_jpg.cpp, see cam_node.ino's
    setup() comment) — GC2145's AWB control functions are all unsupported
    stubs in this driver, and the one plausible byte-order fix
    (jpgSetRgb565BE) was live-tested and made color worse, not better, so
    the default was already correct. Corrected here instead, in software,
    scoped to only the string (stream-URL) source so the webcam path is
    byte-for-byte unchanged.
    """

    def __init__(self, source: int | str = DEVICE_INDEX) -> None:
        self.source = source
        self.cap = cv2.VideoCapture(source)
        if not self.cap.isOpened():
            # Loud and exit per info.md 3.2 — a vision loop silently retrying
            # on a dead camera would burn CPU and never detect anything,
            # which is worse than failing fast and visibly.
            if isinstance(source, str):
                print(
                    f"[ERROR] Could not open video stream at {source!r}.\n"
                    "Likely causes:\n"
                    "  1. Wrong or stale IP — the ESP32-CAM's IP changes "
                    "between networks/reboots; re-check it (e.g. via the "
                    "serial monitor) and pass the current one\n"
                    "  2. ESP32-CAM not powered on, not connected to the "
                    "same network, or not yet finished booting\n"
                    "  3. URL missing the stream path (expected form: "
                    "http://<esp32-ip>/stream)",
                    file=sys.stderr,
                )
            else:
                print(
                    f"[ERROR] Could not open camera at device index {source}.\n"
                    "Likely causes:\n"
                    "  1. Another application is holding the camera "
                    "(close Zoom/FaceTime/other apps using the webcam)\n"
                    "  2. macOS camera permission not granted to this terminal/IDE "
                    "(System Settings -> Privacy & Security -> Camera)\n"
                    "  3. Wrong device index — this device expects index "
                    f"{DEVICE_INDEX} (MacBook built-in camera); if an external "
                    "camera is attached, the index may have shifted",
                    file=sys.stderr,
                )
            sys.exit(1)

        self._warm_up()

    def _warm_up(self, n_frames: int = 10) -> None:
        """Discard the first few frames after opening.

        macOS/AVFoundation cameras return black or garbage frames for a
        short window after VideoCapture opens, while auto-exposure and
        auto-focus settle -- a real bug caught during Day 3 testing, where
        the very first frame grabbed was measured at mean pixel value
        ~0.005 (near-black) and fed the model a meaningless input. Without
        this, every caller of Camera would need to know to skip frames
        itself, which defeats the point of wrapping VideoCapture at all.
        """
        for _ in range(n_frames):
            self.cap.read()

    def read(self) -> np.ndarray:
        """Grab a single BGR frame.

        Raises RuntimeError rather than returning None on a bad read — a
        silent None would propagate into vision.py's preprocessing and fail
        there with a much less useful error, far from the actual cause.
        """
        ok, frame = self.cap.read()
        if not ok:
            raise RuntimeError(
                "Failed to read a frame from the camera — it may have been "
                "disconnected or released by another process mid-run."
            )
        if isinstance(self.source, str):
            frame = self._correct_esp32_color_cast(frame)
        return frame

    @staticmethod
    def _correct_esp32_color_cast(frame: np.ndarray) -> np.ndarray:
        """Gray-world white-balance correction for the ESP32-CAM's red bias.

        Scales each channel so its mean matches the frame's overall gray
        mean — the standard gray-world assumption (average scene color is
        neutral gray), which fits this case well since the measured bias
        is a large, consistent per-channel gain error (R/G=1.98, R/B=2.44
        on a saved reference frame), not per-pixel noise. Clips to uint8
        range since a frame with an unusually bright/saturated red region
        could otherwise push corrected values past 255.
        """
        frame_f = frame.astype(np.float32)
        channel_means = frame_f.mean(axis=(0, 1))  # B, G, R
        gray_mean = channel_means.mean()
        # Avoid div-by-zero on a degenerate (all-black) frame.
        gains = np.where(channel_means > 1e-6, gray_mean / channel_means, 1.0)
        corrected = frame_f * gains
        return np.clip(corrected, 0, 255).astype(np.uint8)

    def encode_jpeg(self, frame: np.ndarray) -> bytes:
        """Encode a BGR frame as JPEG bytes.

        No caller yet — this exists for the Day 8-9 agent, which will send
        snapshots as part of an alert. Implemented now because it is part of
        this class's natural interface (frame in, bytes out, next to read()
        and release()), not because anything calls it yet.
        """
        ok, buf = cv2.imencode(".jpg", frame)
        if not ok:
            raise RuntimeError("Failed to JPEG-encode frame.")
        return buf.tobytes()

    def release(self) -> None:
        """Release the underlying VideoCapture device."""
        self.cap.release()


if __name__ == "__main__":
    # Throwaway smoke test — confirms the class works before vision.py
    # depends on it. Not part of the module's importable interface.
    cam = Camera()
    frame = cam.read()
    print(f"Frame shape: {frame.shape}")
    cam.release()
    print("Camera released OK.")
