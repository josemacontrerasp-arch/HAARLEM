"""Lane B smoke test + the demo spine: build the 13-week forecast on the stub,
flip base -> wet-quarter, show the covenant light move, and drill a cell down to
source records. This is the click-through (PRD section 10) in text form.

Run:  py run_demo.py
"""
from __future__ import annotations

from engine import ForecastConfig, build_forecast, make_stub, validate_transaction


def eur(x: float) -> str:
    return f"{x:>12,.0f}"


def print_forecast(fc, cfg, label):
    print(f"\n=== {label} ({fc.scenario}) ===")
    drivers = fc.drivers()
    net = fc.net_cash()
    bal = fc.running_balance()
    head = fc.covenant_headroom(cfg)
    lights = fc.covenant_lights(cfg)
    print("week  " + "".join(f"{i:>10}" for i in range(len(fc.weeks))))
    for d in ["milestone_billing", "customer_payment", "materials",
              "subcontractor", "vat_remittance", "other"]:
        row = drivers.get(d, [0] * len(fc.weeks))
        if any(abs(v) > 0.5 for v in row):
            print(f"{d[:12]:<12}" + "".join(f"{v:>10,.0f}" for v in row))
    print("-" * 70)
    print("net cash    " + "".join(f"{v:>10,.0f}" for v in net))
    print("balance     " + "".join(f"{v:>10,.0f}" for v in bal))
    print("headroom    " + "".join(f"{v:>10,.0f}" for v in head))
    print("light       " + "".join(f"{l:>10}" for l in lights))


def main():
    cfg = ForecastConfig()
    txns, projects = make_stub(cfg)

    # contract check (Lane A integration: this runs on the real table too)
    problems = [p for t in txns for p in validate_transaction(t)]
    print(f"schema validation: {len(problems)} violation(s)")
    for p in problems:
        print("  !", p)

    base = build_forecast(txns, projects, scenario="base", cfg=cfg)
    print_forecast(base, cfg, "BASE")

    # weather handoff from Lane C: working days lost per weather-exposed project
    wet_shift = {"PRJ-118": 21, "PRJ-091": 28}   # ~3-4 weeks of rain/frost slip
    wet = build_forecast(txns, projects, scenario="wet-quarter", cfg=cfg,
                         weather_shift=wet_shift)
    print_forecast(wet, cfg, "WET-QUARTER")

    # --- drill-down: pick the worst week in wet-quarter and trace it -----------
    net = wet.net_cash()
    worst = min(range(len(net)), key=lambda w: net[w])
    print(f"\n=== DRILL-DOWN: wet-quarter week {worst} "
          f"(net {net[worst]:,.0f}) ===")
    for c in wet.trace(worst):
        print(f"  {c.driver:<18} {c.value:>12,.0f}  {c.computation}")
        print(f"      records={c.contributing_records} "
              f"assumptions={c.assumptions_applied}")


if __name__ == "__main__":
    main()
