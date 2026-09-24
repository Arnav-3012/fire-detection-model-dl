"""Visual-only test of the Stage 6 cloud second opinion -- no gas needed.

The edge loop only asks the cloud on a GAS_HIGH rising edge, which needs
a warmed-up sensor board and a gas source. This script exercises the same
path without either: it pulls live frames from the dashboard relay, runs
them through the LOCAL model (temporal voter included, so "local" means
what fuse() would see), then makes exactly ONE real call to the deployed
Lambda via the same SecondOpinion client edge/main.py uses. The result
lands in the same sidecar, so the Live View panel shows it.

Gas is reported as not-high, so the local level is the vision-only one
(SAFE / WATCH / WARNING) -- rule 1's CRITICAL needs gas.

Needs: the dashboard backend running (it holds the camera relay).
Cost: one Lambda invocation per run, inside the free tier.

    python scripts/test_second_opinion.py
"""

import sys
import time
from pathlib import Path

import cv2
import numpy as np
import requests
import yaml

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "edge"))
from cloud.second_opinion import SecondOpinion  # noqa: E402
from fusion import fuse  # noqa: E402
from vision import VisionModel  # noqa: E402

SNAPSHOT_URL = "http://127.0.0.1:8001/api/camera/snapshot"
FRAMES = 12          # > vision.window (8), so the temporal voter is fully primed
FRAME_GAP_S = 0.12   # ~8 fps, the ESP32-CAM's live rate the voter was tuned for


def grab() -> np.ndarray:
    resp = requests.get(SNAPSHOT_URL, timeout=3)
    if resp.status_code != 200:
        sys.exit(f"camera snapshot failed: HTTP {resp.status_code} {resp.text[:120]!r} "
                 f"(is the dashboard backend running and the camera live?)")
    frame = cv2.imdecode(np.frombuffer(resp.content, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        sys.exit("camera snapshot was not a decodable JPEG")
    return frame


def main() -> None:
    config = yaml.safe_load((_ROOT / "config.yaml").read_text())
    # Force on for this run only -- config.yaml is not modified, and the
    # budget is 1 so this script can never make more than one call.
    config["aws"]["second_opinion"].update(enabled=True, max_calls_per_session=1)

    model = VisionModel(str(_ROOT / "config.yaml"))
    client = SecondOpinion(config)
    if not client.enabled:
        sys.exit("second opinion could not start (see warning above)")

    print(f"Scoring {FRAMES} live frames locally...")
    for _ in range(FRAMES):
        frame = grab()
        result = model.predict_smoothed(frame)
        time.sleep(FRAME_GAP_S)
    level, reason = fuse(vision_fire=bool(result["alarm"]),
                         vision_smoke=bool(result["smoke_sustained"]),
                         gas_high=False, temp_spiking=False)
    print(f"LOCAL: {level.name} ({reason}) p_fire={result['p_fire']:.2f} "
          f"votes={result['votes']} alarm={result['alarm']}")

    # gas_high=True here is the TRIGGER only (a synthetic rising edge);
    # the local level above was fused with gas_high=False.
    client.on_frame(True, frame, level.name, result)
    while client._in_flight.is_set():
        time.sleep(0.05)
    print("Done. Check the 'Cloud second opinion' panel in Live View.")


if __name__ == "__main__":
    main()
