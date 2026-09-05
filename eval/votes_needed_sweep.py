"""Diagnostic-only: sweep TemporalVoter's votes_needed (N) and measure the
effect on neutral_tvfire.mov's block-bar failure vs. fire_candle.mov's
responsiveness.

Mirrors eval/threshold_sweep.py in spirit (a candidate-value sweep that
reports a tradeoff table and a recommendation, edits nothing) but sweeps
`votes_needed` instead of `fire_decision_threshold`, and reuses
eval/run_eval.py's build_model()/run_video() instead of reimplementing the
video-driven eval loop (info.md 3.4 -- no reimplementing detection logic).

WHY this lever, not the model or tau: info.md 4.2's remediation order for a
missed block bar is (1) add hard negatives of that scenario, (2) raise
votes_needed, (3) only then touch the model. Hard negatives for
TV/laptop-fire were already folded into training back in Phase 1 (225 hard
negatives across all 7 categories, tv_laptop_fire included) and the recent
v3 retrain targeted a DIFFERENT gap (small/localized real flames), so step 1
is effectively exhausted for this specific scenario -- votes_needed is the
next untried lever, and this script is that experiment.

WHY votes_needed and not tau: raising tau (the per-frame vote gate) would
make EVERY frame harder to count as a vote, uniformly, regardless of
scenario -- it reshapes the single-frame signal itself. Raising votes_needed
instead asks a narrower question of the EXISTING per-frame signal: does the
fire-like signal persist for longer inside the window? TV footage is
flickering/cutting (scene changes, edits) in a way sustained real flame
is not -- so a stricter persistence requirement should hit TV footage
harder than real fire, which is exactly the asymmetry we want to test for,
without touching the frame-level threshold at all.
"""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "edge"))
from run_eval import ADVERSARIAL_DIR, run_video  # noqa: E402
from vision import VisionModel  # noqa: E402

MODEL_PATH = "models/fire_mnv3.onnx"  # production (v3), per context.md
CONFIG_PATH = "config.yaml"

# 5 = current (plan.md 6.1 initial value). 8 = window size -- unanimous
# agreement, the strictest possible value; going higher is meaningless
# since votes_needed > window can never be satisfied.
CANDIDATE_VOTES_NEEDED = [5, 6, 7, 8]

TVFIRE_BLOCK_BAR = 2          # info.md 4.2, TV showing fire footage
CANDLE_LATENCY_TARGET_S = 3.0  # info.md 4.3, hazard onset -> buzzer, target
CANDLE_LATENCY_BLOCK_S = 10.0  # info.md 4.3, hazard onset -> buzzer, block

CLEAN_SCENARIOS = ["neutral_steam.mov", "neutral_sunset.mov", "neutral_redclothing.mov"]


def sweep_one_votes_needed(n: int) -> dict:
    """Build a fresh VisionModel with this candidate votes_needed and run it
    against all 5 adversarial clips. A fresh model per N (not just a fresh
    voter) matters because build_model() is also how model_path is pinned to
    production v3 -- reusing one model instance across N values would be
    fine for the voter's internal state (run_video() already clears it per
    video) but building fresh keeps this script's structure identical to
    run_eval.py's per-checkpoint pattern, and it is cheap relative to
    inference time.
    """
    with open(CONFIG_PATH) as f:
        base_config = yaml.safe_load(f)
    base_config["vision"]["votes_needed"] = n

    tmp_path = ADVERSARIAL_DIR.parent / "_votes_sweep_tmp.yaml"
    with open(tmp_path, "w") as f:
        yaml.safe_dump(base_config, f)

    model = VisionModel(config_path=str(tmp_path))
    tmp_path.unlink()

    results = {}
    for name in ["neutral_tvfire.mov", "fire_candle.mov"] + CLEAN_SCENARIOS:
        video_path = ADVERSARIAL_DIR / name
        results[name] = run_video(model, video_path)

    return results


def main() -> None:
    print(f"Model: {MODEL_PATH} (production, v3)")
    print(f"Sweeping votes_needed over {CANDIDATE_VOTES_NEEDED} "
          f"(window fixed at 8, frame_threshold/tau fixed at 0.70 -- unchanged)\n")

    all_results = {}
    for n in CANDIDATE_VOTES_NEEDED:
        print(f"--- votes_needed = {n} ---")
        all_results[n] = sweep_one_votes_needed(n)
        for name, r in all_results[n].items():
            tta = f"{r['time_to_first_alarm_s']:.2f}s" if r["time_to_first_alarm_s"] is not None else "-"
            print(f"  {name:<26} alarms={r['alarm_count']:>2}  max_p_fire={r['max_p_fire']:.4f}  time_to_alarm={tta}")
        print()

    # Comparison table
    header = (f"{'votes_needed':>12} | {'tvfire alarms':>13} | {'tvfire vs bar (<=2)':>20} | "
              f"{'candle alarms':>13} | {'candle time-to-alarm':>21} | {'regression on clean 3':>22}")
    print(header)
    print("-" * len(header))

    recommendation = None
    for n in CANDIDATE_VOTES_NEEDED:
        r = all_results[n]
        tvfire = r["neutral_tvfire.mov"]
        candle = r["fire_candle.mov"]

        tvfire_alarms = tvfire["alarm_count"]
        tvfire_verdict = "PASS" if tvfire_alarms <= TVFIRE_BLOCK_BAR else "FAIL"

        candle_alarms = candle["alarm_count"]
        candle_tta = candle["time_to_first_alarm_s"]
        candle_tta_str = f"{candle_tta:.2f}s" if candle_tta is not None else "NEVER"

        regressions = [name for name in CLEAN_SCENARIOS if r[name]["alarm_count"] > 0]
        regression_str = ", ".join(regressions) if regressions else "none"

        print(f"{n:>12} | {tvfire_alarms:>13} | {tvfire_verdict + f' ({tvfire_alarms} alarms)':>20} | "
              f"{candle_alarms:>13} | {candle_tta_str:>21} | {regression_str:>22}")

        # Selection criteria, evaluated in ascending N order so the FIRST
        # passing N found is automatically the lowest (least aggressive)
        # one -- same "sweep low to high, take the first pass" logic as
        # threshold_sweep.py uses for fire_decision_threshold.
        if recommendation is None:
            tvfire_ok = tvfire_alarms <= TVFIRE_BLOCK_BAR
            candle_latency_ok = (
                candle_tta is not None
                and candle_tta <= CANDLE_LATENCY_TARGET_S
                and candle_tta <= CANDLE_LATENCY_BLOCK_S
            )
            no_regression = len(regressions) == 0
            if tvfire_ok and candle_latency_ok and no_regression:
                recommendation = n

    print(f"\ninfo.md 4.2 block bar: TV/laptop-fire alarms <= {TVFIRE_BLOCK_BAR}")
    print(f"info.md 4.3 latency bars: hazard-to-buzzer target <= {CANDLE_LATENCY_TARGET_S}s, block <= {CANDLE_LATENCY_BLOCK_S}s")
    print("Selection rule: lowest (least aggressive) votes_needed that (a) brings tvfire alarms")
    print("<= 2, (b) keeps candle time-to-alarm within BOTH the 3s target and 10s block bar, and")
    print("(c) introduces zero new alarms on the 3 already-passing clean scenarios.\n")

    if recommendation is not None:
        r = all_results[recommendation]
        print(f"RECOMMENDATION (not a decision, per info.md 7 -- developer confirms): "
              f"votes_needed = {recommendation}")
        print(f"  tvfire: {r['neutral_tvfire.mov']['alarm_count']} alarms (was 7 at votes_needed=5)")
        print(f"  candle: {r['fire_candle.mov']['alarm_count']} alarms, "
              f"time-to-alarm {r['fire_candle.mov']['time_to_first_alarm_s']:.2f}s")
        print("  clean 3 scenarios: no new alarms")
    else:
        print("NO tested votes_needed value achieves all three conditions simultaneously.")
        print("Per info.md section 7: reporting this plainly rather than picking the closest value.")
        print("The developer should decide the next step (e.g. accept a partial improvement,")
        print("revisit hard negatives specifically for TV/laptop-fire content, or accept the")
        print("open item as a documented limitation).")


if __name__ == "__main__":
    main()
