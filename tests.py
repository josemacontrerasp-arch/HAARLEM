"""Engine invariants — runnable with zero deps:  py tests.py

These guard the contract so a refactor (or Lane A's real data) can't silently
corrupt the forecast. Each test asserts one property of the spine.
"""
from __future__ import annotations

from datetime import date

from engine import (
    ForecastConfig,
    Transaction,
    biggest_movers,
    build_forecast,
    compute_vat_remittances,
    make_stub,
    validate_transaction,
)

PASS, FAIL = 0, 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}")


def t_stub_is_schema_clean():
    txns, _ = make_stub()
    violations = [v for t in txns for v in validate_transaction(t)]
    check("stub has zero schema violations", not violations)


def t_balance_is_opening_plus_cumsum():
    txns, projects = make_stub()
    fc = build_forecast(txns, projects)
    net, bal = fc.net_cash(), fc.running_balance()
    run = fc.opening_balance
    ok = True
    for i in range(len(net)):
        run += net[i]
        ok = ok and abs(run - bal[i]) < 0.01
    check("running balance == opening + cumulative net cash", ok)


def t_trace_sums_to_cell():
    txns, projects = make_stub()
    fc = build_forecast(txns, projects)
    drivers = fc.drivers()
    ok = True
    for w in range(len(fc.weeks)):
        for d, row in drivers.items():
            traced = sum(c.value for c in fc.trace(w, d))
            ok = ok and abs(traced - row[w]) < 0.01
    check("trace(week, driver) sums to the driver cell (drill-down is exact)", ok)


def t_actuals_excluded_from_forward_cash():
    txns, projects = make_stub()
    fc = build_forecast(txns, projects)
    used = {r for c in fc.contributions for r in c.contributing_records}
    actuals = {t.record_id for t in txns if t.status == "actual"}
    check("actual rows never appear as forward cash events", not (used & actuals))


def t_weather_moves_revenue_not_materials():
    txns, projects = make_stub()
    base = build_forecast(txns, projects, scenario="base")
    wet = build_forecast(txns, projects, scenario="wet-quarter",
                         weather_shift={"PRJ-118": 21, "PRJ-091": 28})
    # materials timeline must be identical (committed -> doesn't slip)
    same_materials = base.drivers()["materials"] == wet.drivers()["materials"]
    # but total inflow timing must change (revenue slips) -> there is a mover
    movers = biggest_movers(base, wet)
    check("weather slips revenue but NOT committed materials (the squeeze)",
          same_materials and len(movers) > 0)


def t_unmapped_does_not_crash():
    txns, projects = make_stub()
    # the stub already includes an UNMAPPED row; build must succeed and bucket it
    fc = build_forecast(txns, projects)
    check("UNMAPPED row is handled without crashing", fc is not None)


def t_vat_remittance_computed_when_absent():
    # rows with VAT but no explicit vat_remittance -> engine synthesises one
    txns = [Transaction(
        record_id="r1", source_system="exact", source_file="f", source_row=1,
        opco="O", date=date(2026, 4, 10), gl_account_native="8000",
        gl_account_unified="1300", driver_type="milestone_billing",
        amount_excl_vat=10000, vat_amount=2100, amount_incl_vat=12100,
        status="open_ar", counterparty="Gemeente X", project_id="P1")]
    vat = compute_vat_remittances(txns)
    check("VAT remittance computed from vat column when none supplied",
          len(vat) == 1 and vat[0].amount_incl_vat < 0)


def t_scenario_only_changes_weather():
    # base vs wet on the SAME data: only difference is the weather_shift input
    txns, projects = make_stub()
    base = build_forecast(txns, projects, scenario="base")
    wet = build_forecast(txns, projects, scenario="wet-quarter",
                         weather_shift={"PRJ-118": 21})
    # totals over the horizon should match (cash moves in time, isn't created/destroyed
    # within horizon unless it slips past week 12) -> at least materials total identical
    check("scenario perturbs only weather (materials total unchanged)",
          abs(sum(base.drivers()["materials"]) - sum(wet.drivers()["materials"])) < 0.01)


def main():
    for fn in [
        t_stub_is_schema_clean,
        t_balance_is_opening_plus_cumsum,
        t_trace_sums_to_cell,
        t_actuals_excluded_from_forward_cash,
        t_weather_moves_revenue_not_materials,
        t_unmapped_does_not_crash,
        t_vat_remittance_computed_when_absent,
        t_scenario_only_changes_weather,
    ]:
        fn()
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
