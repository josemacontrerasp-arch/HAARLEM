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
    build_all_opcos,
    build_forecast,
    compute_vat_remittances,
    covenant,
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


def t_opcos_reconcile_to_portfolio():
    txns, projects = make_stub()
    views = build_all_opcos(txns, projects)
    portfolio = views["PORTFOLIO"]
    opco_views = [v for k, v in views.items() if k != "PORTFOLIO"]
    pnet = portfolio.net_cash()
    ok = True
    for w in range(len(pnet)):
        summed = sum(v.net_cash()[w] for v in opco_views)
        ok = ok and abs(summed - pnet[w]) < 0.01
    check("sum of per-opco net cash == consolidated (no two numbers disagree)", ok)


def t_all_covenant_metrics_run():
    txns, projects = make_stub()
    ok = True
    for metric in ("min_liquidity", "leverage", "dscr"):
        cfg = ForecastConfig(covenant_metric=metric)
        fc = build_forecast(txns, projects, cfg=cfg)
        head = fc.covenant_headroom()
        lights = fc.covenant_lights()
        ok = ok and len(head) == len(fc.weeks) and len(lights) == len(fc.weeks)
        ok = ok and all(l in ("green", "amber", "red") for l in lights)
    check("all three covenant metrics compute headroom + lights", ok)


def t_covenant_breach_detected():
    # force a breach by setting an impossibly high liquidity floor
    txns, projects = make_stub()
    cfg = ForecastConfig(covenant_metric="min_liquidity", covenant_threshold=10_000_000)
    fc = build_forecast(txns, projects, cfg=cfg)
    breach = covenant.first_breach_week(fc.covenant_lights())
    check("an unreachable threshold is flagged as a breach", breach == 0)


def t_payment_lag_recovered():
    from datetime import timedelta
    from engine import estimate_payment_lag
    base = date(2026, 1, 1)
    # government invoices all paid 45 days later; sme 21 days later
    pairs = {
        "government": [(base, base + timedelta(days=45)) for _ in range(10)],
        "sme": [(base, base + timedelta(days=21)) for _ in range(10)],
    }
    coeffs = estimate_payment_lag(pairs)
    check("payment-lag estimator recovers planted lags (45/21d)",
          coeffs["government"].value == 45 and coeffs["sme"].value == 21)


def t_weather_coeffs_recovered():
    from engine import WeatherObs, estimate_weather_coeffs, predict_days_lost
    # construct data where days_lost = 0.02*rain + 0.5*frost exactly
    obs = [WeatherObs(rain, frost, 0.02 * rain + 0.5 * frost)
           for rain in (0, 10, 50, 120) for frost in (0, 1, 3)]
    c = estimate_weather_coeffs(obs)
    ok = (abs(c["rain"].value - 0.02) < 1e-6 and abs(c["frost"].value - 0.5) < 1e-6
          and c["rain"].r2 > 0.99)
    # 100mm rain + 4 frost days -> round(0.02*100 + 0.5*4) = round(4.0) = 4
    ok = ok and predict_days_lost(100, 4, c) == 4
    check("weather estimator recovers planted coefficients + predicts slip", ok)


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
        t_opcos_reconcile_to_portfolio,
        t_all_covenant_metrics_run,
        t_covenant_breach_detected,
        t_payment_lag_recovered,
        t_weather_coeffs_recovered,
    ]:
        fn()
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
