# Altis Weather-Aware Cash Flow Forecast — Engine (Lane B)

One reconciliation-and-forecasting engine: a 13-week cash forecast where **every
number traces to its source journal line**, with a weather toggle that cascades
causally to the covenant warning light. Thin role views read one engine, so no
two numbers disagree.

See [`altis_prd.md`](altis_prd.md) (product) and [`altis_lanes.md`](altis_lanes.md) (team split).

## Quick start

```bash
py run_demo.py      # build base + wet-quarter, move the covenant light, drill a cell
py tests.py         # 13 invariants (trace exactness, opco reconciliation, covenant, ML)
```

The engine core (schema, forecast, covenant, vat, config, stub) is **pure stdlib**.
`learn.py` needs numpy; reading Lane A's real table needs duckdb (parquet) — see
`requirements.txt`.

## Architecture — the spine A and C plug into

```
Lane A (data)                Lane B (engine = this)                 Lane C (experience)
raw exports ──reconcile──►  Transaction[] + Project[]
                            (Contract v1, engine/schema.py)
                                     │
                            build_forecast(scenario, opco) ──► Forecast object
                                     │                          • drivers / net_cash
                            weather_shift {proj: days_lost} ◄───── Lane C owns this
                                     │                          • running_balance
                            covenant.headroom_metric ──────────► • covenant_headroom + lights
                                     │                          • trace(week, driver)
                                     └──────────────────────────► one object, all role views
```

Key files:

| File | Responsibility |
|---|---|
| `engine/schema.py` | Contract v1 (`Transaction`), `Project`/`Milestone`, and `TracedValue` |
| `engine/forecast.py` | the spine: `build_forecast`, `build_all_opcos`, `trace`, `to_dict`, `biggest_movers` |
| `engine/covenant.py` | all 3 covenant rules (min_liquidity / leverage / dscr), config-selected |
| `engine/vat.py` | quarterly BTW remittance from the VAT column |
| `engine/learn.py` | interpretable ML coefficients (payment lag, weather slip) |
| `engine/load.py` | read Lane A's real parquet/duckdb/csv → engine objects + recon summary |
| `engine/config.py` | every tunable assumption in one place |
| `engine/stub.py` | synthetic data so all lanes build in parallel |

## How forecasting works (the status lifecycle)

The engine reads the unified table and forecasts forward cash from `status`:

| status | meaning | engine treatment |
|---|---|---|
| `actual` | cash already moved | anchors the opening balance |
| `open_ar` | invoice issued, unpaid | inflow at `date + payment_lag(segment)` |
| `open_ap` | committed cost, unpaid | outflow at `date` |
| `wip` | work done, not invoiced | becomes milestone billing → inflow after lag |

**Weather operator:** for weather-exposed projects, a scenario shifts the
*revenue side* (billing/collections, milestone-tied subcontractor) right by the
days lost — but **committed materials stay put**. That gap is the cash squeeze.

**Traceability:** every cash contribution is a `TracedValue` carrying its source
records, assumptions, scenario and formula. `trace(week, driver)` is just a
filter — drill-down is exact (a test asserts traces sum to the cell).

## Integration TODOs (waiting on inputs)

- [ ] **Covenant doc** → set `covenant_metric` + numbers in `config.py`. All three
      rule types are already implemented, so this is a config flip, not a rewrite.
- [ ] **Lane A's reconciled v1 table** → point `load_transactions(path)` at it.
- [ ] **Lane A: `counterparty_segment`** → drop the temp lookup in `config.py`.
- [ ] **Lane A: project/milestone table** → feed via `load_projects(json)`.
- [ ] **Lane C: weather shift** → already the exact `{project_id: days_lost}` input.

## Assumptions (documented for the judges)

- No covenant terms were provided → default is a **minimum-liquidity** covenant
  (consolidated cash ≥ threshold, tested weekly). Swappable in `config.py`.
- Payment lags are placeholder coefficients until estimated from real paired
  invoice/payment data via `engine/learn.py`.

## Data handling

Altis data is **event-licensed**: do not commit it; delete all copies within 3
days of the event (PRD §11). `.gitignore` excludes the data folders.
