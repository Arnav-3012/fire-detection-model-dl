"""Throwaway camera smoke test. Not part of the edge module.

Opens the default webcam, shows the live feed with FPS overlaid, exits on 'q'.
Run this to confirm a camera is reachable before edge/camera.py exists (Day 3).
"""

import sys
import time

import cv2

DEVICE_INDEX = 0


def main() -> None:
    cap = cv2.VideoCapture(DEVICE_INDEX)

    if not cap.isOpened():
        print(
            "[ERROR] Could not open camera at index "
            f"{DEVICE_INDEX}.\n"
            "Likely causes:\n"
            "  1. Another app is holding the camera (Zoom, Teams, browser tab) — close it.\n"
            "  2. OS camera permission not granted to the terminal/IDE running this script.\n"
            "  3. Wrong device index — try DEVICE_INDEX = 1, 2, ... in this file."
        )
        sys.exit(1)

    prev_time = time.time()
    fps = 0.0

    print("Camera opened. Press 'q' in the video window to quit.")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("[ERROR] Failed to read frame from camera. Exiting.")
                break

            now = time.time()
            dt = now - prev_time
            prev_time = now
            if dt > 0:
                fps = 1.0 / dt

            cv2.putText(
                frame,
                f"FPS: {fps:.1f}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 255, 0),
                2,
            )

            cv2.imshow("FireWatch camera smoke test", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
