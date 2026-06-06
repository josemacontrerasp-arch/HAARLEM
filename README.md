# Altis Groep — Weather-Aware 13-Week Cash-Flow Forecast & Role-Based Dashboards

[![tests](https://github.com/josemacontrerasp-arch/HAARLEM/actions/workflows/tests.yml/badge.svg)](https://github.com/josemacontrerasp-arch/HAARLEM/actions/workflows/tests.yml)

**One reconciled engine. Four accounting systems. Four role views. Five cash-flow
drivers. A weather toggle that cascades all the way to the covenant light — and
every single number clicks down to the journal line behind it.**

Built for **Altis Groep**: a private-equity-backed portfolio of Dutch roofing
companies, each on a different accounting system, all under one loan covenant.
Finance leadership needs a short-horizon cash forecast they can *defend to the
board* — not a dashboard they have to take on faith.

> **Tier 3 (Full Forecast Platform) delivered** — all four roles, the complete
> five-driver model, LLM-assisted GL mapping, four-system reconciliation, full
> click-through auditability, and edge-case resilience. See the
> [Tier checklist](#tier-achievement--every-requirement-mapped) and the
> [judging-criteria map](#how-this-maps-to-the-judging-criteria) below.

---

## 🔗 Live demo & quick start

| | |
|---|---|
| **Live app** | https://haarlem-app-utundmvdr9tv6jwewjt32s.streamlit.app/ |
| **Access** | Password-protected (licensed data). **Password: provided in the submission form.** |
| **Run locally** | `pip install -r requirements.txt` → `streamlit run app.py` |
| **Headless demo** | `py run_demo.py` (forecast + covenant + audit-trail walkthrough) |
| **Verify everything** | `py tests.py` → **18 engine invariants, all passing** |

The live app is gated by a password only to protect the licensed data and the
demo's API budget — it is **not** a paywall. Judges receive the password with the
submission. With no password configured (a local clone), the app runs open.

### 2-minute judge demo path (the whole story, click by click)

1. **CFO tab** → read the 13-week forecast, the driver breakdown, and the covenant
   traffic light. Note the **liquidity warning week**.
2. Sidebar → **Scenario → Wet Quarter**. Watch the covenant light and the weekly
   numbers move. (Then **Dry Quarter** to see it recover.)
3. **CFO tab → Trace drill-down** → pick the week that dipped → see the exact
   driver contributions, the **assumptions applied** (payment lag, weather slip),
   the scenario toggle, and the **source GL record IDs** behind the number.
4. **Opco MD tab** → per-opco WIP exposure and project risk cards.
5. **Project Lead tab** → next invoiceable milestone and how weather shifts it.
6. **PE Board tab** → consolidated covenant status + biggest scenario movers.
7. **GL Mapping tab** → the LLM proposes each account's mapping with confidence +
   rationale; flips between the keyless heuristic and the live OpenAI backend;
   flags the genuinely ambiguous accounts for a controller; agreement rate scored.

---

## What it is, in one breath

> A **scenario-driven forecasting engine, statistically calibrated.**

The scenario engine is the spine: deterministic, auditable, counterfactual-native
("what happens to cash if the next quarter is wet?"). Statistics plays a small,
honest supporting role — it fits just **two interpretable coefficients** that feed
the timing rules:

1. **payment lag** per customer segment (days from invoice to cash), and
2. **working-days-lost** per mm of rain / per frost day.

That's the whole use of statistical methods ([`engine/learn.py`](engine/learn.py)).
No black-box predictor sits on the critical path, so every figure stays explainable
and every assumption stays overridable. A CFO can see exactly why a number moved —
the only kind of forecast a CFO will actually trust on a Monday morning.

---

## Why this isn't a BI dashboard with a weather multiplier

The naïve version multiplies cash by "0.8 in a wet quarter." That's untraceable
and wrong: weather doesn't shrink cash, it **moves it in time**. We treat weather
as a **causal delay operator** ([`engine/weather.py`](engine/weather.py),
[`engine/forecast.py`](engine/forecast.py)):

```
rain / frost
   → fewer workable days        (CAO "onwerkbaar weer" / UAV 2012 thresholds, KNMI-calibrated)
   → weather-dependent milestones slip later
   → billing shifts right
   → collections shift further right (by each customer's payment lag)
   → liquidity dips             ← THE SQUEEZE: materials were already paid
   → covenant headroom moves
```

Committed **materials stay put** while **billing slides** — that gap *is* the cash
squeeze, and it falls straight out of the model instead of being faked. A unit test
(`weather slips revenue but NOT committed materials`) asserts exactly this.

**Live weather, honestly scoped:** the **Project Lead** tab pulls a **real, current
Open-Meteo forecast per opco location** (keyless) and scores it with the roofing
unworkable-day thresholds — the near-term schedule-risk signal. Because no forecast
reaches 13 weeks out, the **scenario engine** runs on **KNMI climatology** for the
full horizon. Live signal where it's real; climatology where it must be.

---

## The four roles (one engine, no two numbers disagree)

Every view reads the **same computed forecast object** ([`engine/forecast.py`](engine/forecast.py)).
Consistency is structural, not maintained by hand — proven by the test
`sum of per-opco net cash == consolidated`.

| Role | The question it answers | What it shows |
|---|---|---|
| **PE Board** | "Are we safe on the covenant before the meeting?" | Consolidated portfolio, covenant traffic light, quarterly leverage test, biggest scenario movers |
| **CFO** | "What's my 13-week cash by driver, and what happens in a wet quarter?" | Full forecast, driver breakdown, scenario toggles, cross-opco compare, trace drill-down |
| **Opco MD** | "What's my WIP exposure and which projects are at risk?" | Per-opco WIP, project risk signals, materials/subcontractor commitments, weather-shifted milestones |
| **Project Lead** | "When's my next invoice and will weather delay it?" | Next invoiceable milestone, materials outflows ahead of execution, schedule risk |

## The five drivers (modelled separately, each independently tunable)

| Driver | What it represents | Behaviour under weather |
|---|---|---|
| **Materials outflow** | Roofing materials, ordered & paid ahead of execution | **Committed — does not slip** (this is what creates the squeeze) |
| **Subcontractor** | Costs tied to milestone progress | Tied to the schedule |
| **Milestone billing** | Invoiceable milestones; completion creates a receivable (VAT-aware) | Slips right when the milestone slips |
| **Customer payment behaviour** | Receivable lands at invoice date **+ lag**, per customer segment | Collections shift further right |
| **Weather impact** | Not a line item — the **operator** that shifts the timing of all the above | The cause of every shift |

Cash is never lumped. Click any week and it decomposes into exactly these streams.
Every driver and key assumption is **live-tunable in the sidebar** ("Tune drivers &
assumptions"): payment lag, weather sensitivity, materials & subcontractor outflow,
opening cash and the covenant floor — the forecast, covenant light and audit trail
all recompute instantly, and the toggle that produced a number is itself traceable.
Defaults live in [`engine/config.py`](engine/config.py).

---

## Four-system reconciliation into one schema

All **four** accounting systems are ingested by per-system adapters into one
canonical transaction record ([`engine/schema.py`](engine/schema.py)). **36,976
rows, 0 schema violations, 0 unmapped accounts.**

| System | Adapter | Opco | Source shape (each different) |
|---|---|---|---|
| **Gilde** | [`ingest_gilde.py`](ingest_gilde.py) | Heeze | Per-account GL `.xlsx` (Debet/Credit, BTW codes) |
| **Yuki** | [`ingest_yuki.py`](ingest_yuki.py) | Brunssum | Per-account GL exports with metadata header blocks |
| **Snelstart** | [`ingest_snelstart.py`](ingest_snelstart.py) | Winschoten | GL sheets + a Company-E invoice list → `open_ar`; MMEM → WIP accrual |
| **Exact** | [`ingest_exact.py`](ingest_exact.py) | Andijk | Aggregated monthly *Netto-omzet* matrix (net of VAT → grossed up) |

`py ingest_all.py` merges all four, checks `record_id` uniqueness, validates the
schema, and writes the reconciled `data/transactions.csv` + `data/reconciliation.json`.

### LLM-assisted GL mapping (reviewable & auditable by a controller)

[`llm_gl_mapping.py`](llm_gl_mapping.py) — a model proposes how each native GL
account maps into the unified chart (**unified account + cash-flow driver**) with
a **confidence** and a **one-line rationale**; a controller approves or rejects each
one; **every decision is logged** to `data/mapping_suggestions.json`; suggestions
are scored against the controller-approved chart (`data/gl_mapping.csv`) and an
**agreement rate** is reported.

- **Three backends, one interface:** OpenAI → Anthropic → a deterministic **keyless
  heuristic**, auto-selected by which API key is present. The heuristic is the
  default so the demo, tests and a fresh clone always run with no key and no network.
- On the real chart the keyless heuristic reaches **83% unified / 92% driver
  agreement** and flags exactly the two genuinely ambiguous accounts (the
  Memoriaal debit/credit split and the Gilde-routed reverse-charge) for the
  controller — which is the honest behaviour.
- Live in the dashboard's **GL Mapping** tab, and from the CLI:
  `py llm_gl_mapping.py --demo-new` (also demos a brand-new, never-seen account).

---

## Architecture (ingestion → reconciliation → driver modelling → scenarios → roles)

A clean pipeline, each stage swappable — the exact platform-level separation the
brief asks for at Tier 3.

```
 ingest_*.py              engine/                                    app.py
 ┌────────────┐   ┌──────────────────────────────────────────┐   ┌───────────┐
 │ Gilde      │   │ schema   → one canonical transaction record │   │ CFO       │
 │ Yuki       │──▶│ load     → reconcile + project pipeline      │──▶│ Opco MD   │
 │ Snelstart  │   │ drivers  → 5 streams, week by week           │   │ Proj Lead │
 │ Exact      │   │ weather  → scenario delay operator           │   │ PE Board  │
 └────────────┘   │ covenant → headroom + traffic light          │   │ GL Mapping│
   GL mapping     │ learn    → 2 calibrated coefficients          │   └───────────┘
   (LLM-assisted, │ trace()  → every cell → source journal line   │   one object,
    controller-   └──────────────────────────────────────────────┘   all views
    approved)
```

| File | Responsibility |
|---|---|
| `ingest_gilde / yuki / snelstart / exact / all .py` | Per-system adapters (**all four**) → one canonical schema |
| [`llm_gl_mapping.py`](llm_gl_mapping.py) | LLM-assisted GL mapping (OpenAI/Anthropic + keyless heuristic), confidence + rationale + approve/reject log + agreement rate |
| [`mapping_panel.py`](mapping_panel.py) | Frontend-agnostic Streamlit panel for the controller review (one function) |
| [`data/gl_mapping.csv`](data/gl_mapping.csv) | Chart-of-accounts mapping (controller-approved rules) |
| [`engine/schema.py`](engine/schema.py) | The canonical contract: transaction, project/milestone, **trace metadata** |
| [`engine/load.py`](engine/load.py) | Load reconciled data, normalise opcos, build the real-data state |
| [`engine/forecast.py`](engine/forecast.py) | The spine: 13-week forecast, 5 drivers, `trace()`, per-opco + consolidated |
| [`engine/weather.py`](engine/weather.py) | Keyless Open-Meteo → working-days-lost (the delay operator) |
| [`engine/learn.py`](engine/learn.py) | Statistical calibration of the two coefficients |
| [`engine/covenant.py`](engine/covenant.py) | Covenant headroom + traffic light (all three covenant forms) |
| [`engine/ebitda.py`](engine/ebitda.py), [`engine/vat.py`](engine/vat.py) | EBITDA from P&L; quarterly BTW (VAT) remittance |
| [`engine/pipeline.py`](engine/pipeline.py) | Revenue-calibrated forward project & WIP pipeline |
| [`app.py`](app.py) | Streamlit dashboard — the four role views + GL Mapping, light/dark theme |

---

## Traceability — the heart of it (every number is defensible)

Every computed value is **born carrying its own trace** (source records,
assumptions applied, scenario, toggle values, formula) — `TracedValue` in
[`engine/schema.py`](engine/schema.py). Drill-down isn't bolted on afterwards;
it's a filter over data that was always there. The controller walkthrough:

```
Wet quarter, week 9 liquidity dips
  → decomposes into the five drivers
  → biggest mover: deferred milestone billing
  → traces to specific weather-exposed roofs whose schedules slipped
  → invoices pushed right, collections pushed further right by payment lag
  → click the figure → the actual reconciled GL line IDs + the mapping rule that placed them
```

`forecast.trace(week, driver)` returns every contributing record. The test
`trace(week, driver) sums to the driver cell` asserts the trace sums **exactly** to
the number it explains — auditability is a proven invariant, not a claim.

The drill-down shows, per contribution: the **full reconciled GL line** (record id ·
system/unified account · date · gross · source file:row), the **assumptions applied**,
the scenario + weather toggle, and an honest **provenance** label —
*Real GL* vs *Modeled (pipeline)* — so a controller always knows which figures come
straight from the source data and which are the revenue-calibrated forward model.

---

## Scenarios (base / wet-quarter / dry-quarter)

Toggled in the sidebar; each perturbs **only the weather input**, which then
cascades through the timing rules to the right downstream numbers — never a blanket
multiplier. Proven by the test `scenario perturbs only weather (materials total
unchanged)`. The PE Board view surfaces the **biggest movers vs base** so the board
sees *what* changed and *why*.

---

## Covenant (and a real finding: liquidity vs leverage)

[`engine/covenant.py`](engine/covenant.py) implements **all three common covenant
forms** — minimum liquidity, Net-Debt/EBITDA leverage, and DSCR — selectable by a
single config flag. So when the real covenant document arrives, it's a **config
change, not a rebuild** (proven by `all three covenant metrics compute…`).

**The finding:** a quarterly trailing-12m **leverage** covenant barely reacts to
13-week cash timing, so we surface the weather cascade on the weekly **liquidity**
buffer (the CFO's early warning), while **leverage** is the quarterly board test.
Both are computed; neither contradicts the other. The traffic light flags amber as
headroom approaches the threshold and red on breach.

---

## Built-in resilience (survives the edge cases the brief names)

- **New / unknown GL account** → flagged `UNMAPPED`, **kept (never dropped)**,
  bucketed so the forecast doesn't break. `llm_gl_mapping.py --demo-new` shows the
  model proposing a mapping for it, held for controller approval. (Test:
  `UNMAPPED row is handled without crashing`.)
- **Late correction journal** → modelled via the status lifecycle
  (`actual` vs accrual vs `wip`), so corrections don't double-count cash. (Test:
  `actual rows never appear as forward cash events`.)
- **Slipping project** → that's the weather operator's *normal* behaviour, not a
  failure mode.
- **New opco** → a configuration entry, not a rebuild (`build_all_opcos`).

---

## VAT & Dutch GAAP

- **BTW (VAT):** reverse-charge (`verlegd`), 21%, 9% and 0% lines handled per
  system; quarterly BTW remittance computed in [`engine/vat.py`](engine/vat.py)
  (test: `VAT remittance computed from vat column when none supplied`).
- **WIP / periodisering:** Snelstart Memoriaal (MMEM) debit entries become **WIP
  accruals** (revenue recognised, not yet invoiced) and flow as weather-slippable
  future inflows; credit-side reversals don't double-count.

---

## Assumptions (documented, every one overridable — in `engine/config.py`)

Where a precise input wasn't present in our data drop, we use **explicit,
industry-standard assumptions** rather than inventing numbers. The brief explicitly
allows *real OR realistic* data.

| Input | Assumption | Basis |
|---|---|---|
| Covenant form | Net Debt / EBITDA, trailing-12m, quarterly (all 3 forms coded) | Lender's standard form; config-selectable |
| EBITDA | revenue × **10%** | Typical roofing margin (~8–15%) |
| Net debt | **3.0×** EBITDA | Typical PE entry leverage |
| Covenant cap | **3.5×** | Typical mid-market covenant |
| Opening cash | ~1.75 months of revenue | No bank export was provided |
| Project / WIP pipeline | calibrated to each opco's **real** revenue run-rate | No WIP file in our drop ([`engine/pipeline.py`](engine/pipeline.py)) |
| Weather impact | threshold "unworkable-day" model, KNMI-calibrated per quarter | Dutch **CAO Onwerkbaar weer / UAV 2012** + **KNMI** — see [`altis_weather_model_validation.md`](altis_weather_model_validation.md) |

---

## Run it / reproduce it

```bash
pip install -r requirements.txt

streamlit run app.py              # the dashboard (4 roles + GL Mapping, scenarios, drill-down)
py run_demo.py                    # headless: forecast + covenant + audit-trail walkthrough
py ingest_all.py                  # reconcile all FOUR systems → data/transactions.csv
py llm_gl_mapping.py --demo-new   # LLM GL mapping: suggestions + approve/reject + agreement rate
py tests.py                       # 18 engine invariants (all pass)
```

**Dependencies** are in [`requirements.txt`](requirements.txt). The engine core is
pure Python standard library; `numpy` fits the two coefficients, `duckdb` reads
reconciled tables, `pandas/altair/pydeck` power the UI, `openai` enables the LLM
mapping backend (optional — falls back to the keyless heuristic).

**LLM backend key (optional):** copy `.env.example` → `.env` and paste
`OPENAI_API_KEY` (auto-loaded, gitignored), or set it in Streamlit Cloud Secrets.
See [`DEPLOY.md`](DEPLOY.md) for one-click deployment.

### The 18 invariants (`tests.py`)

Traceability sums exactly · running balance = opening + Σ net cash · actuals never
double-counted · weather slips revenue but **not** committed materials · UNMAPPED
survives · VAT remittance computed · scenarios perturb only weather · per-opco =
consolidated · all 3 covenant metrics · breach detected · payment-lag recovered ·
weather coefficients recovered · LLM mapping agreement · reverse-charge rule ·
unknown→UNMAPPED flagged · Exact adapter reconciles.

---

## Tier achievement — every requirement mapped

**Tier 1 — CFO Dashboard ✅**
- Ingestion from an accounting system ✅ (four of them) · driver separation ✅ ·
  13-week week-by-week forecast ✅ · covenant headroom flagged ✅ · scenario
  toggle ✅ · traceability ✅. *Bonus:* weather integrated ✅ · 2nd+ system
  reconciled ✅ · payment-lag as a separate driver ✅.

**Tier 2 — Multi-Role Dashboard ✅**
- Everything in Tier 1 ✅ · Opco MD view (WIP exposure, project risk,
  materials/subcontractor commitments) ✅ · **3+ systems** reconciled ✅ (four) ·
  **weather-to-schedule translation** (not a flat multiplier) ✅ · three scenarios
  affecting the right numbers ✅. *Bonus:* LLM-assisted GL mapping ✅ · Project
  Lead view ✅.

**Tier 3 — Full Forecast Platform ✅**
- All four roles ✅ · **full five-driver model**, independently tunable ✅ ·
  survives new GL account / late correction / slipping project ✅ · **LLM-assisted
  GL mapping, reviewable & auditable** ✅ · new opco = config change ✅ · logical
  architecture (ingestion → reconciliation → drivers → scenarios → presentation) ✅
  · one schema / one source of truth ✅ · full click-through auditability ✅ ·
  documentation a controller can use ✅.

## Required deliverables (01–06) — mapped

| # | Deliverable | Where |
|---|---|---|
| 01 | Ingestion + reconciliation into a unified schema | `ingest_*.py`, `engine/schema.py`, `engine/load.py` (4 systems, 0 violations) |
| 02 | 13-week forecast by driver stream | `engine/forecast.py`, CFO tab |
| 03 | Covenant headroom indicator, flagged at threshold | `engine/covenant.py`, traffic light in every covenant panel |
| 04 | Scenario toggle (base/wet/dry) affecting the right numbers | sidebar + `engine/weather.py` (cascade), tested |
| 05 | Traceability of any figure → drivers → source | `TracedValue` + `forecast.trace()`, CFO drill-down |
| 06 | README + run instructions + architecture | this file + [`DEPLOY.md`](DEPLOY.md) + [`altis_weather_model_validation.md`](altis_weather_model_validation.md) |

## Submission checklist (the brief's quick-reference — all ✅)

- ✅ Data from ≥1 accounting system ingested and reconciled — **four** systems
- ✅ Cash-flow drivers as separate streams — **five**, never lumped
- ✅ 13-week week-by-week forecast
- ✅ Covenant headroom flagged near threshold
- ✅ Scenario toggle works — base / wet / dry
- ✅ Any figure traces back to drivers and source data
- ✅ Role-based views specific to roofing/PE — not generic BI
- ✅ Weather affects **timing** meaningfully — causal delay, not a flat multiplier
- ✅ Architecture absorbs a new GL account / late correction without breaking
- ✅ VAT & Dutch GAAP handled (BTW, WIP/periodisering)
- ✅ Same source of truth feeds forecast **and** dashboards (proven by test)
- ✅ Controller-level audit-trail walkthrough in the demo
- ✅ Realistic deployment path (live on Streamlit Cloud; no re-platforming)
- ✅ README with run instructions (this file)

---

## How this maps to the judging criteria

| Criterion (weight) | Where we earn it |
|---|---|
| **Impact & Relevance** (24 / 40%) | A forecast a CFO would open Monday: the materials-vs-billing **squeeze** made visible; the **liquidity-vs-leverage** distinction (a real operational insight); role views built for roofing under PE, not generic BI. |
| **Technical Depth** (19 / 32%) | **Four** heterogeneous systems reconciled into one schema (0 violations); survives UNMAPPED / late corrections / slips; per-opco **= consolidated**, proven by test; 18 passing invariants; end-to-end live deployment. |
| **Auditability** (17 / 28%) | Every cell → driver → assumption → toggle → **source GL line**; trace **sums exactly** (tested); LLM mapping logged with confidence + rationale + approve/reject + agreement rate; one source of truth feeds all views. |
| **User Experience** (8) | Clean themed UI (light/dark), four role tabs, scenario toggle, graceful fallbacks (self-healing real-data loader, keyless mapping fallback). |
| **Documentation** (6) | This README + `DEPLOY.md` + `altis_weather_model_validation.md`; inline rationale throughout the code. |
| **Polish** (5) | Consistent visual design, branded logo (light/dark aware), no-crash edge handling. |
| **Setup & Onboarding** (4) | `pip install -r requirements.txt` → `streamlit run app.py`; or just open the live URL. |
| **Reproducibility & Code Quality** (4) | 18 invariant tests, clean module boundaries, pure-stdlib engine core. |
| **Deployment Readiness** (3) | Already deployed (Streamlit Cloud) with secrets + password gate; one schema feeds everything; new opco = config. |
| **Innovation** (10) | Weather as a **causal delay operator** (not a multiplier); scenario-driven **+** statistically calibrated with only two interpretable coefficients; the cash squeeze surfaced structurally; LLM GL mapping that **degrades gracefully to a keyless heuristic** so it always runs and is always auditable. |

---

## Repository guide

```
app.py                     Streamlit dashboard (4 role tabs + GL Mapping, themes)
mapping_panel.py           Drop-in controller-review panel (one function)
llm_gl_mapping.py          LLM-assisted GL mapping (OpenAI/Anthropic/heuristic)
ingest_{gilde,yuki,snelstart,exact}.py, ingest_all.py   Per-system adapters
run_demo.py                Headless forecast + covenant + audit walkthrough
tests.py                   18 engine invariants
engine/                    schema · load · forecast · weather · learn · covenant
                           · ebitda · vat · pipeline · config · stub
data/                      gl_mapping.csv · reconciled transactions · P&L · audit log
altis_weather_model_validation.md   Weather model, validated vs CAO/UAV + KNMI
DEPLOY.md                  Streamlit Cloud deployment guide
```

---

## Data handling (license compliance)

All Altis data is anonymised and **licensed for the event only**. It must be
deleted from every storage location within **3 days** of the hackathon and must not
be redistributed. The live deployment is **password-protected**; API keys live only
in the host's secret store (never committed); `.env` and `.streamlit/secrets.toml`
are gitignored.
