"""Lane B smoke test + the demo spine: build the 13-week forecast on the stub,
flip base -> wet-quarter, show the covenant light move, find the biggest mover,
and drill that cell down to source records. This is the click-through (PRD
section 10) in text form.

Run:  py run_demo.py
"""
from __future__ import annotations

import json

from engine import (
    ForecastConfig,
    biggest_movers,
    build_forecast,
    covenant,
    make_stub,
    validate_transaction,
)


def print_forecast(fc, label):
    print(f"\n=== {label} ({fc.scenario}) ===")
    drivers = fc.drivers()
    n = len(fc.weeks)
    print("week        " + "".join(f"{i:>10}" for i in range(n)))
    for d in ["milestone_billing", "customer_payment", "materials",
              "subcontractor", "vat_remittance", "other"]:
        row = drivers.get(d, [0] * n)
        if any(abs(v) > 0.5 for v in row):
            print(f"{d[:12]:<12}" + "".join(f"{v:>10,.0f}" for v in row))
    print("-" * (12 + 10 * n))
    print("net cash    " + "".join(f"{v:>10,.0f}" for v in fc.net_cash()))
    print("balance     " + "".join(f"{v:>10,.0f}" for v in fc.running_balance()))
    print("headroom    " + "".join(f"{v:>10,.0f}" for v in fc.covenant_headroom()))
    print("light       " + "".join(f"{l:>10}" for l in fc.covenant_lights()))


def main():
    cfg = ForecastConfig()
    txns, projects = make_stub(cfg)

    problems = [p for t in txns for p in validate_transaction(t)]
    print(f"schema validation: {len(problems)} violation(s)")
    for p in problems:
        print("  !", p)

    base = build_forecast(txns, projects, scenario="base", cfg=cfg)
    print_forecast(base, "BASE")

    wet_shift = {"PRJ-118": 21, "PRJ-091": 28}   # Lane C's weather handoff
    wet = build_forecast(txns, projects, scenario="wet-quarter", cfg=cfg,
                         weather_shift=wet_shift)
    print_forecast(wet, "WET-QUARTER")

    breach = covenant.first_breach_week(wet.covenant_lights())
    print(f"\nfirst covenant warning (wet): week {breach}")

    # --- the demo move: biggest mover base -> wet, then drill it ---------------
    print("\n=== BIGGEST MOVERS (base -> wet-quarter) ===")
    movers = biggest_movers(base, wet, top=5)
    for m in movers:
        print(f"  week {m.week:>2}  {m.driver:<18} "
              f"{m.base_value:>12,.0f} -> {m.scenario_value:>12,.0f}  "
              f"(delta {m.delta:>+12,.0f})")

    # Drill where the deferred cash LANDS (scenario_value != 0) so the trace
    # carries the weather_slip + payment_lag story, not an emptied week.
    target = next((m for m in movers if abs(m.scenario_value) > 0.5), movers[0])
    print(f"\n=== DRILL-DOWN: wet week {target.week}, driver '{target.driver}' "
          f"(deferred cash landing here) ===")
    for c in wet.trace(target.week, target.driver):
        print(f"  {c.value:>12,.0f}  {c.computation}")
        print(f"      records={c.contributing_records} "
              f"assumptions={c.assumptions_applied}")

    # --- prove the single serialisable object Lane C consumes -----------------
    with open("forecast_base.json", "w", encoding="utf-8") as fh:
        json.dump(base.to_dict(), fh, indent=2)
    print("\nwrote forecast_base.json (the object Lane C reads)")


if __name__ == "__main__":
    main()
