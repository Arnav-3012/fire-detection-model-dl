"""Stage 2 offline verification: the gas verdict now comes from the
board's STATE, with config thresholds used only as a legacy fallback.

Extracts main.py's decision block and drives it directly. No hardware.
"""
import sys, threading, types, time
sys.path.insert(0, "edge")
for m in ("serial",):
    try: __import__(m)
    except ImportError: sys.modules[m] = types.ModuleType(m)
from fusion import compute_gas_high, fuse, Level

# Real stale config values — the whole point is that these disagree
# with the 12-bit board.
TH = {"mq2_warn":115.57,"mq2_danger":174.04,"mq135_warn":98.77,"mq135_danger":146.44}
WARMUP = 240.0

def verdict(readings, first_reading, now):
    """Mirror of edge/main.py's Stage 2 block."""
    state = readings["state"]; gated = False; fellback = False
    if readings["mq2"] is None or readings["mq135"] is None or first_reading is None:
        gas_high = False
    elif state is not None:
        gas_high = state == "GAS_HIGH"
        if state in ("WARMUP","BASELINE_CAPTURE"): gated = True
    else:
        fellback = True
        if now - first_reading < WARMUP:
            gated = True; gas_high = False
        else:
            gas_high = compute_gas_high(float(readings["mq2"]),float(readings["mq135"]),TH)
    return gas_high, gated, fellback

fails = 0
def check(desc, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(f"[{'PASS' if ok else 'FAIL'}] {desc:<62} -> {got}")
    if not ok: print(f"        expected {want}")

print("=== PRIMARY PATH: board state is the verdict ===")
R = lambda mq2,mq135,st: {"mq2":mq2,"mq135":mq135,"state":st}
check("GAS_HIGH -> gas_high True", verdict(R(900,300,"GAS_HIGH"),0,10), (True,False,False))
check("ok -> gas_high False", verdict(R(245,60,"ok"),0,10), (False,False,False))
check("ok(BASELINE_TROUBLE) -> False", verdict(R(245,60,"ok(BASELINE_TROUBLE)"),0,10), (False,False,False))
check("WARMUP -> False + GATED", verdict(R(145,42,"WARMUP"),0,10), (False,True,False))
check("BASELINE_CAPTURE -> False + GATED", verdict(R(200,55,"BASELINE_CAPTURE"),0,10), (False,True,False))

print("\n=== THE BUG STAGE 2 FIXES: stale config vs board ===")
# 245 is a NORMAL 12-bit reading, but it's ABOVE stale mq2_warn=115.57.
old = compute_gas_high(245,60,TH)
new = verdict(R(245,60,"ok"),0,10)[0]
check(f"mq2=245 normal: OLD host logic said gas_high={old}", old, True)
check("   NEW firmware verdict correctly says False", new, False)
print("       ^ this false CRITICAL on every normal reading is what Stage 2 removes")

# And the converse: board says GAS_HIGH while stale thresholds disagree.
check("board GAS_HIGH is honoured even if config would say False",
      verdict(R(100,40,"GAS_HIGH"),0,10)[0], True)
check("   (stale config alone would have said False here)",
      compute_gas_high(100,40,TH), False)

print("\n=== NO-DATA PATH ===")
check("no readings yet -> False", verdict(R(None,None,None),None,10), (False,False,False))
check("state but no numbers -> False", verdict(R(None,None,"ok"),None,10), (False,False,False))

print("\n=== FALLBACK PATH: legacy 2-field firmware ===")
check("legacy, inside warm-up -> False + GATED + fellback",
      verdict(R(200,60,None),0.0,10.0), (False,True,True))
check("legacy, past warm-up, above stale warn -> True + fellback",
      verdict(R(200,60,None),0.0,WARMUP+1), (True,False,True))
check("legacy, past warm-up, below stale warn -> False + fellback",
      verdict(R(50,40,None),0.0,WARMUP+1), (False,False,True))
check("firmware path does NOT set fellback", verdict(R(900,300,"GAS_HIGH"),0,10)[2], False)

print("\n=== warm-up timer must NOT suppress a real board GAS_HIGH ===")
# t=0: board says GAS_HIGH immediately. Old code would gate this for 240s.
g,gated,_ = verdict(R(900,300,"GAS_HIGH"),0.0,1.0)
check("GAS_HIGH at t=1s (inside old 240s gate) still fires", (g,gated), (True,False))

print("\n=== end-to-end through fuse() ===")
g,_,_ = verdict(R(900,300,"GAS_HIGH"),0,10)
lvl,reason = fuse(vision_fire=True,vision_smoke=False,gas_high=g,temp_spiking=False)
check("fire + board GAS_HIGH -> CRITICAL", lvl, Level.CRITICAL)
g,_,_ = verdict(R(245,60,"ok"),0,10)
lvl,reason = fuse(vision_fire=True,vision_smoke=False,gas_high=g,temp_spiking=False)
check("fire + board ok -> WARNING (vision-only cap holds)", lvl, Level.WARNING)
g,_,_ = verdict(R(900,300,"GAS_HIGH"),0,10)
lvl,reason = fuse(vision_fire=False,vision_smoke=False,gas_high=g,temp_spiking=False)
check("no vision + GAS_HIGH -> WARNING (rule 3)", lvl, Level.WARNING)

print(f"\n{'ALL CHECKS PASSED' if not fails else str(fails)+' CHECK(S) FAILED'}")
sys.exit(1 if fails else 0)
