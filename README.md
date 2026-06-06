# Altis — Weather-Aware 13-Week Cash Flow Forecast

**One reconciled engine. Four role views. A weather toggle that cascades all the
way to the covenant light — and every number clicks down to the journal line
behind it.**

Built for Altis Groep: a private-equity-backed portfolio of Dutch roofing
companies, each on a different accounting system, all sitting under one loan
covenant. Finance leadership needs a short-horizon cash forecast they can *defend*
to the board — not a dashboard they have to take on faith.

---

## What it is, in one breath

> A **scenario-driven forecasting engine, statistically calibrated.**

The scenario engine is the spine: deterministic, auditable, counterfactual-native
("what happens to cash if the next quarter is wet?"). Statistics plays a small,
honest supporting role — it fits just **two interpretable coefficients** that feed
the timing rules:

1. **payment lag** per customer segment (days from invoice to cash), and
2. **working-days-lost** per mm of rain / per frost day.

That's the whole use of statistical methods. No black-box predictor sits on the
critical path, so every figure stays explainable and every assumption stays
overridable. A CFO can see exactly why a number moved — which is the only kind of
forecast a CFO will actually trust on a Monday morning.

---

## Why this isn't a BI dashboard with a weather multiplier

The naïve version multiplies cash by "0.8 in a wet quarter." That's untraceable
and wrong: weather doesn't shrink cash, it **moves it in time**. Our model treats
weather as a **causal delay operator**:

```
rain / frost
   → fewer workable days
   → weather-dependent milestones slip later
   → billing shifts right
   → collections shift further right (by each customer's payment lag)
   → liquidity dips        ← the squeeze: materials were already paid
   → covenant headroom moves
```

Committed **materials stay put** while **billing slides** — that gap *is* the cash
squeeze, and it falls straight out of the model instead of being faked.

---

## The four roles (one engine, no two numbers disagree)

Every view reads the **same computed forecast object**. Consistency is structural,
not maintained by hand.

| Role | The question it answers | What it shows |
|---|---|---|
| **PE Board** | "Are we safe on the covenant before the meeting?" | Consolidated portfolio, covenant traffic light, quarterly leverage test |
| **CFO** | "What's my 13-week cash by driver, and what happens in a wet quarter?" | Full forecast, driver breakdown, scenario toggles, cross-opco compare |
| **Opco MD** | "What's my WIP exposure and which projects are at risk?" | Per-opco WIP, project risk signals, materials/subcontractor commitments |
| **Project Lead** | "When's my next invoice and will weather delay it?" | Next invoiceable milestone, materials outflows, schedule risk |

## The five drivers (modelled separately, each independently tunable)

| Driver | What it represents |
|---|---|
| **Materials outflow** | Roofing materials, ordered & paid ahead of execution (committed — doesn't slip) |
| **Subcontractor** | Costs tied to milestone progress (slips with weather) |
| **Milestone billing** | Invoiceable milestones; completion creates a receivable (VAT-aware) |
| **Customer payment behaviour** | Receivable arrives at invoice date + lag, per customer segment |
| **Weather impact** | Not a line item — the operator that shifts the timing of all of the above |

Cash is never lumped. Click any week and it decomposes into exactly these streams.

---

## Architecture

A clean pipeline, each stage swappable:

```
 ingest_*.py              engine/                                    app.py
 ┌────────────┐   ┌──────────────────────────────────────────┐   ┌───────────┐
 │ Gilde      │   │ schema   → one canonical transaction record │   │ CFO       │
 │ Yuki       │──▶│ load     → reconcile + project pipeline      │──▶│ Opco MD   │
 │ Snelstart  │   │ drivers  → 5 streams, week by week           │   │ Proj Lead │
 │ Exact      │   │ weather  → scenario delay operator           │   │ PE Board  │
 └────────────┘   │ covenant → headroom + traffic light          │   └───────────┘
   GL mapping     │ learn    → 2 calibrated coefficients          │   one object,
   (LLM-assisted, │ trace()  → every cell → source journal line   │   all views
    controller-   └──────────────────────────────────────────────┘
    approved)
```

| File | Responsibility |
|---|---|
| `ingest_gilde.py`, `ingest_yuki.py`, `ingest_snelstart.py`, `ingest_exact.py`, `ingest_all.py` | Per-system adapters (**all four systems**) → one canonical schema |
| `llm_gl_mapping.py` | LLM-assisted GL mapping (OpenAI or Anthropic, with a keyless heuristic fallback): model suggests unified account + driver with confidence + rationale → controller approves/rejects → logged & agreement-rate scored |
| `data/gl_mapping.csv` | Chart-of-accounts mapping (controller-approved rules) |
| `engine/schema.py` | The canonical contract: transaction, project/milestone, **trace metadata** |
| `engine/load.py` | Load reconciled data, normalise opcos, build the real-data state |
| `engine/forecast.py` | The spine: 13-week forecast, drivers, `trace()`, per-opco + consolidated |
| `engine/weather.py` | Keyless Open-Meteo → working-days-lost (the delay operator) |
| `engine/learn.py` | Statistical calibration of the two coefficients |
| `engine/covenant.py` | Covenant headroom + traffic light (leverage / liquidity) |
| `engine/ebitda.py`, `engine/vat.py` | EBITDA from P&L; quarterly BTW remittance |
| `app.py` | Streamlit dashboard — the four role views |

---

## Run it

```bash
pip install -r requirements.txt

streamlit run app.py        # the dashboard (four role views, scenario toggle, drill-down)
py run_demo.py              # headless: forecast + covenant + an audit-trail walkthrough
py ingest_all.py            # reconcile all FOUR systems → data/transactions.csv
py llm_gl_mapping.py --demo-new   # LLM-assisted GL mapping: suggestions + controller approve/reject + agreement rate
                                  #   keyless heuristic by default. For the LLM backend, copy .env.example -> .env and
                                  #   paste OPENAI_API_KEY (or ANTHROPIC_API_KEY); it's auto-loaded and gitignored.
py tests.py                 # 18 engine invariants (traceability, reconciliation, mapping, covenant…)
```

The engine core is pure Python standard library; `numpy` powers the two
coefficients, `duckdb` reads reconciled tables, `streamlit` runs the UI.

---

## Traceability — the heart of it

Every computed value is born carrying its own trace (source records, assumptions,
scenario, toggle values, formula). Drill-down isn't bolted on afterwards — it's a
filter over data that was always there. The walkthrough a controller would run:

```
Wet quarter, week 9 liquidity dips
  → decomposes into the five drivers
  → biggest mover: deferred milestone billing
  → traces to specific weather-exposed roofs whose schedules slipped
  → invoices pushed right, collections pushed further right by payment lag
  → click the figure → the actual reconciled GL lines + the mapping rule that placed them
```

`forecast.trace(week, driver)` returns every contributing record. A test asserts
traces sum **exactly** to the cell they explain.

---

## Built-in resilience (survives the edge cases)

- **New / unknown GL account** → flagged `UNMAPPED`, kept (never dropped), bucketed
  so the forecast doesn't break — and `llm_gl_mapping.py --demo-new` shows the model
  proposing a mapping for it, held for the controller to approve.
- **Late correction journal** → modelled via the status lifecycle (`actual` vs
  accrual vs WIP), so corrections don't double-count cash.
- **Slipping project** → that's the weather operator's normal behaviour, not a
  failure mode.
- **New opco** → a configuration entry, not a rebuild (`build_all_opcos`).

---

## Assumptions (documented, every one overridable)

We were not given covenant terms, cost data, debt figures, or a project/WIP file.
Rather than invent precise numbers, we use **explicit industry-standard assumptions**
(all in `engine/config.py`):

| Input | Assumption | Basis |
|---|---|---|
| Covenant | Net Debt / EBITDA, trailing-12m, tested quarterly | Lender's stated form |
| EBITDA | revenue × **10%** | Typical roofing margin (~8–15%); only one opco had costs, at an implausible 66% → not used |
| Net debt | **3.0×** EBITDA | Typical PE entry leverage |
| Covenant cap | **3.5×** | Typical mid-market covenant |
| Opening cash | ~1.75 months of revenue | No bank export was provided |
| Project pipeline | calibrated to each opco's real revenue | No WIP file was provided (the brief allows *realistic* data) |
| Weather impact | threshold "unworkable-day" model, KNMI-calibrated per quarter | Anchored to Dutch **CAO Onwerkbaar weer / UAV 2012** + **KNMI** norms — see [`altis_weather_model_validation.md`](altis_weather_model_validation.md) |

**Liquidity vs leverage (a real finding):** a quarterly TTM leverage covenant
barely reacts to 13-week cash timing, so the weather cascade is surfaced on the
weekly **liquidity** buffer (the CFO's early warning), while **leverage** is the
quarterly board test. Both are computed; neither contradicts the other.

---

## Data handling

All Altis data is anonymised and **licensed for the event only**. It must be
deleted from every location within 3 days of the hackathon. Raw exports and the
P&L file are git-ignored and must not be redistributed.

---

## How this maps to the scoring

| Criterion | Where we earn it |
|---|---|
| **Impact & Relevance** | A defensible forecast a CFO would open Monday; the materials-vs-billing squeeze; liquidity-vs-leverage distinction |
| **Technical Depth** | **4 systems** reconciled into one schema; survives UNMAPPED / corrections / slips; per-opco = consolidated, proven by test |
| **Auditability** | Every cell → driver → assumption → toggle → source line; LLM mapping suggestions logged with confidence + rationale + approve/reject; one source of truth feeds all four roles |
| **Innovation** | Weather as a causal delay operator (not a multiplier); scenario-driven + statistically calibrated; the squeeze made visible; LLM GL mapping that degrades to a keyless heuristic so the demo always runs |
