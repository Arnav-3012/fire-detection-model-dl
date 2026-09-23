"""Stage 1 offline verification: feed _parse_line() every line shape the
ESP32 firmware actually prints and assert the outcome.

No hardware, no network. Run: python3 verify_stage1.py
"""
import sys, threading, types
sys.path.insert(0, "edge")
for m in ("serial", "yaml"):
    try: __import__(m)
    except ImportError: sys.modules[m] = types.ModuleType(m)
import sensors

def fresh():
    r = sensors.SensorReader.__new__(sensors.SensorReader)
    r._lock = threading.Lock()
    r._mq2 = r._mq135 = r._state = None
    r._thresholds = {}
    r._first_reading_monotonic = None
    return r

OK = ("245,60,ok,baseline_mq2=180,warn_mq2=237.5,danger_mq2=306.2,"
      "baseline_mq135=50,warn_mq135=98.7,danger_mq135=127.3")

# (line, expected latest() or None meaning "must be ignored")
CASES = [
    # --- the three real reading shapes: MUST parse ---
    ("145,42",                      {"mq2":145,"mq135":42,"state":None}),
    ("145,42,WARMUP",               {"mq2":145,"mq135":42,"state":"WARMUP"}),
    ("200,55,BASELINE_CAPTURE",     {"mq2":200,"mq135":55,"state":"BASELINE_CAPTURE"}),
    (OK,                            {"mq2":245,"mq135":60,"state":"ok"}),
    (OK.replace("245,60,ok","900,300,GAS_HIGH"),
                                    {"mq2":900,"mq135":300,"state":"GAS_HIGH"}),
    (OK.replace(",ok,",",ok(BASELINE_TROUBLE),"),
                                    {"mq2":245,"mq135":60,"state":"ok(BASELINE_TROUBLE)"}),
    # --- real firmware non-reading lines: MUST be ignored ---
    ("[SUSPECT_JUMP] mq2=900(flagged) mq135=300",                    None),
    ("[WARMUP_STABLE] warmup gate cleared via slope stability after 412s", None),
    ("[WARMUP_BACKSTOP] warmup gate cleared via WARMUP_MAX_SECONDS timeout", None),
    ("[BASELINE_TROUBLE] captured baseline outside expected range",  None),
    ("[BASELINE_TROUBLE_CLEARED] tracked baseline back within range", None),
    ("BASELINE_CAPTURE done: mq2=180 mq135=50",                      None),
    ("FireWatch Phase 13b sensor board -- MEASUREMENT FOUNDATION FIXED", None),
    ("Connecting to WiFi",                                           None),
    ("Connected, IP: 192.168.1.42",                                  None),
    ("NOTE: WiFi connectivity only -- no data transmitted yet",       None),
    # --- garbage: MUST be ignored ---
    ("", None), ("garbage", None), ("12,", None), ("145,42,BOGUS_STATE", None),
    (",,", None), ("abc,def", None),
]

fails = 0
for line, expect in CASES:
    r = fresh()
    r._parse_line(line.encode() + b"\r\n")
    got = r.latest()
    ignored = got == {"mq2":None,"mq135":None,"state":None}
    if expect is None:
        ok = ignored
        want = "IGNORED"
    else:
        ok = got == expect
        want = str(expect)
    if not ok: fails += 1
    print(f"[{'PASS' if ok else 'FAIL'}] {line[:52]:<54} -> {got if not ignored else 'IGNORED'}")
    if not ok: print(f"        expected: {want}")

# --- threshold behaviour ---
print()
r = fresh()
r._parse_line(OK.encode())
t = r.thresholds()
exp_t = {"baseline_mq2":180.0,"warn_mq2":237.5,"danger_mq2":306.2,
         "baseline_mq135":50.0,"warn_mq135":98.7,"danger_mq135":127.3}
ok = t == exp_t; fails += not ok
print(f"[{'PASS' if ok else 'FAIL'}] six live thresholds captured -> {t}")

r._parse_line(b"145,42,WARMUP")
ok = r.thresholds() == exp_t; fails += not ok
print(f"[{'PASS' if ok else 'FAIL'}] thresholds PERSIST across a later WARMUP line")

r2 = fresh()
r2._parse_line(b"245,60,ok,baseline_mq2=180,warn_mq2=237.5")  # partial set
ok = r2.thresholds() == {}; fails += not ok
print(f"[{'PASS' if ok else 'FAIL'}] partial threshold set ignored, not half-applied -> {r2.thresholds()}")

r3 = fresh()
ok = r3.thresholds() == {}; fails += not ok
print(f"[{'PASS' if ok else 'FAIL'}] thresholds() empty before any OK line")

# --- regression: the exact bug Stage 1 fixes ---
print()
r4 = fresh()
for l in ["145,42,WARMUP","200,55,BASELINE_CAPTURE",OK]:
    r4._parse_line(l.encode())
ok = r4.latest()["mq2"] is not None; fails += not ok
print(f"[{'PASS' if ok else 'FAIL'}] REGRESSION: ESP32 lines no longer all dropped "
      f"(old parser left this None) -> {r4.latest()}")

print(f"\n{'ALL CHECKS PASSED' if not fails else str(fails)+' CHECK(S) FAILED'}")
sys.exit(1 if fails else 0)
