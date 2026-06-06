# PRD — Altis Weather-Aware Cash Flow Forecast

**One-liner:** One reconciliation-and-forecasting engine (the single source of truth) that produces a 13-week cash forecast where every number is clickable down to its source journal line, with thin role-specific views over the same engine, and a weather toggle that cascades causally from rain days all the way to the covenant warning light.

**Not:** a four-screen BI dashboard with a weather multiplier bolted on.

---

## 1. Context

Altis Groep is a PE-backed portfolio of roofing companies. Each operating company (opco) runs a different accounting system (Gilde, Yuki, Exact, Snelstart). Finance leadership needs a short-horizon (13-week) cash forecast that:

- merges all systems into one consistent picture,
- reflects the reality that **weather stops roofing work**, which delays billing, which delays cash,
- and warns before the portfolio breaches its loan covenant.

The product must be **defensible**: a controller has to be able to trace any number back to source, and the board has to trust it.

## 2. Goals / Non-goals

**Goals**
- A 13-week cash forecast built from a genuinely reconciled foundation (3+ systems).
- Cash modelled as **separate, independently tunable drivers** — never lumped.
- Weather modelled as a **causal delay operator** on the project schedule, not a flat multiplier.
- **Full traceability**: every forecast number → driver → assumption → scenario toggle → source record.
- Covenant headroom computed correctly and flagged before breach.
- Four role views, all reading the **same engine** (no two numbers disagree).

**Non-goals**
- Generic BI prettiness. UI polish is the lowest-scoring axis.
- A SaaS-style P&L. This is project/WIP/cash, Dutch GAAP, VAT timing.
- A learned end-to-end ML cash predictor (low data, un-auditable, bad at counterfactuals). ML is used only to estimate individual driver coefficients (see §6).
- A fully-working fourth ingestion adapter. The architecture must *allow* a fourth opco as config; we ship three working.

## 3. Users & roles

All four views are windows onto one engine. Build CFO + Opco MD fully; Board and Project Lead are lightweight summary cards over the same data.

| Role | Core question | View |
|---|---|---|
| PE Board | "Are we safe on the covenant before the board meeting?" | Covenant headroom traffic light + consolidated portfolio summary |
| CFO | "What's my 13-week cash by driver, and what happens in a wet quarter?" | Full forecast, driver breakdown, scenario toggles, cross-opco compare |
| Opco MD | "What's my WIP exposure and which projects are at risk?" | Per-opco WIP, project risk signals, materials/subcontractor commitments |
| Project Lead | "When's my next invoice and will weather delay it?" | Per-project next invoiceable milestone, materials outflows, schedule risk |

## 4. Core requirements

1. **Ingestion** — adapter per accounting system → canonical transaction records.
2. **Reconciliation** — GL mapping collapses 4 systems' accounts into one canonical chart. Includes LLM-assisted mapping: model *suggests*, controller *approves*, decision is *logged*. LLM suggestions validated against the provided mapping file to demonstrate agreement rate.
3. **Driver model** — five independent, tunable streams (§6).
4. **Forecast** — 13-week, week-by-week, net cash + running balance.
5. **Scenario engine** — base / wet-quarter / dry-quarter. A scenario changes **only the weather input**; everything downstream recomputes. That is what makes toggles affect "the right downstream numbers" while staying traceable.
6. **Weather causal chain** — weather → workable days → schedule slip on weather-exposed tasks → shifted milestones → shifted billing → shifted collections → moved covenant headroom.
7. **Covenant** — implement the threshold and calculation rule *exactly* as specified in the covenant doc. Flag amber/red near threshold.
8. **Traceability/audit** — every forecast cell carries trace metadata (§7). Drill-down: cell → driver decomposition → assumption → toggle → source journal line → mapping rule that placed it.

## 5. Canonical data model (the contract — lock this first)

**Transaction record**
```
txn_id, source_system, source_record_id,
booking_date, cash_date,
canonical_account, source_account,
amount (signed EUR), vat_amount, vat_code,
direction (in/out), counterparty, counterparty_segment,
project_id (nullable), opco,
driver (one of 5), mapping_rule_id, mapping_source (manual|llm_approved)
```

**Project / milestone record**
```
project_id, opco, customer, customer_segment,
contract_value, wip_to_date, percent_complete,
weather_exposure (0..1),
milestones: [{ milestone_id, description, planned_date, amount,
               completion_stage, status (pending|invoiced|paid),
               weather_dependent (bool) }],
materials_schedule:    [{ date, amount }],            # committed outflows
subcontractor_schedule:[{ date, amount, milestone_id }]
```

**Trace metadata (attached to every computed forecast value)**
```
value, week, driver,
contributing_records: [source_record_id...],
assumptions_applied:  [assumption_id...],
scenario, toggle_values: {...},
computation: "<short formula string>"
```

## 6. The five drivers (week-by-week)

1. **Materials outflow(w)** = committed material payments scheduled in week *w* (from `materials_schedule`), with timing shifted by weather slip on the parent project.
2. **Subcontractor payments(w)** = subcontractor costs tied to milestones expected to complete in week *w*.
3. **Milestone billing(w)** = invoiceable milestone amounts whose completion lands in week *w* → creates a receivable (incl. VAT timing).
4. **Customer payment behaviour** = receivable arrives at `cash_date = invoice_date + payment_lag(customer_segment)`. So inflow(w) = billings invoiced in `(w − lag)`.
5. **Weather impact** = *not a separate line*. It is the operator that shifts `planned_date` of weather-dependent milestones later by `working_days_lost`, cascading into drivers 1–4.

`net_cash(w) = inflows(w) − outflows(w)` → running balance → `covenant_headroom(w) = metric(w) − threshold` per the covenant rule.

**Legit ML (optional, scoped):** small regressions that estimate single interpretable coefficients feeding the drivers — `working_days_lost per mm rain / frost day`, and `payment_lag per customer_segment`. Output is an inspectable, overridable number, never a black-box forecast.

## 7. Scenario mechanics

- **base:** forecast weather as-is → expected workable days.
- **wet-quarter:** raise rain/frost frequency → more days lost → milestones slip right.
- **dry-quarter:** fewer days lost → milestones hold or pull earlier.

Each scenario perturbs only the weather input; the engine recomputes drivers, forecast, and covenant headroom. Trace metadata records which scenario + toggle values produced each cell.

## 8. How features map to the score

| Feature | Scores on |
|---|---|
| Traceability drill-down | Auditability (28%) + Impact — **highest single lever** |
| Real reconciliation, one source of truth | Technical Depth + Impact ("no two numbers disagree") |
| Weather causal cascade | Impact + Innovation |
| Correct Dutch GAAP / VAT / covenant math | Credibility moat across all criteria |
| Thin role views over one engine | Breadth credit, cheap |
| LLM GL mapping w/ human review + log | Innovation + Auditability |

## 9. Scope: MVP → stretch (this is also the cut list)

Cut from the bottom when time runs short.

1. **MVP (must ship):** 3 systems reconciled into canonical schema; 3 drivers (materials, subcontractor, milestone billing); 13-week forecast; covenant flag; base scenario; **traceability drill-down working end to end**.
2. Payment-lag driver + customer segments.
3. Weather causal chain + wet/dry scenarios.
4. CFO + Opco MD views fully built.
5. LLM-assisted GL mapping with review + log.
6. Board + Project Lead summary cards.
7. ML coefficient estimation; fourth-opco-as-config demonstration.

## 10. Demo narrative (the product *is* the demo)

Board/CFO view, covenant green → flip to wet-quarter → buffer slides to amber, weeks 8–11 dip → click week-9 dip → decomposes to drivers → biggest mover is deferred milestone billing → click it → traces to three weather-exposed roofs whose schedules slipped → invoices pushed right → collections pushed right by payment lag → drill one project (Opco MD view): WIP, slipped milestone, materials *already paid* despite billing slip (the squeeze) → drill to Project Lead: next invoice now week 11 not week 8, six rain days → click the materials figure → lands on actual GL lines from Exact + Snelstart, reconciled, mapped by a controller-approved rule.

## 11. Tech & data notes

- Stack is our choice — judged on results, not tools.
- Weather source: **Open-Meteo** (free, clean historical + forecast API). Points are in the schedule transfer function, not the data source.
- **Data handling:** all Altis data is licensed for the event only. Delete every copy (local, cloud, repo, notebook, VM) within 3 days after the hackathon.
