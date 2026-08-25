"""Webcam capture for FireWatch edge loop.

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
    """

    def __init__(self, device_index: int = DEVICE_INDEX) -> None:
        self.device_index = device_index
        self.cap = cv2.VideoCapture(device_index)
        if not self.cap.isOpened():
            # Loud and exit per info.md 3.2 — a vision loop silently retrying
            # on a dead camera would burn CPU and never detect anything,
            # which is worse than failing fast and visibly.
            print(
                f"[ERROR] Could not open camera at device index {device_index}.\n"
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
        return frame

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
