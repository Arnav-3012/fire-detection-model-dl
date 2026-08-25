"""Edge loop v1: camera -> vision -> print.

No temporal voting, sensors, or fusion here -- those are Day 4, Day 6, and
Day 7 respectively (info.md 3.4). This is deliberately the simplest possible
loop that proves the camera -> ONNX -> console path works end to end.
"""

from camera import Camera
from vision import VisionModel


def format_result(result: dict[str, bool | float]) -> str:
    """Render one prediction as a single console line.

    Fire gets a distinct, unmissable line when it fires (the eventual real
    alarm case); anything else prints as a quieter one-line status so a
    human watching the console can tell "notable" from "normal" at a glance.
    """
    if result["fire"]:
        return f"FIRE {result['p_fire']:.2f}"
    return f"neutral (fire={result['p_fire']:.2f}, smoke={result['smoke']})"


def main() -> None:
    camera = Camera()  # warm-up handled internally, per edge/camera.py
    model = VisionModel()

    print("FireWatch edge loop v1 running. Press Ctrl+C to stop.")
    try:
        while True:
            frame = camera.read()
            result = model.predict(frame)
            print(format_result(result))
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        camera.release()


if __name__ == "__main__":
    main()
