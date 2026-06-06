# Team Lanes — Altis Cash Flow Forecast

Three people. Split by the **seams of the engine**, not by role-view. The classic 3-person hackathon failure is three parallel workstreams that only meet at hour 20 and don't fit. We avoid that by locking one shared contract first, then everyone builds against it — not against each other's unfinished work.

---

## The one rule

**Before anyone writes feature code, we lock two things together:**
1. The **canonical schema** (transaction + project/milestone records).
2. The **trace metadata format** (what travels with every number).

Both are defined in the PRD §5. Once locked, **the lead ships a small hand-made stub dataset** so all three lanes can develop in parallel immediately. Stub gets swapped for real reconciled data at integration time.

---

## Kickoff (first ~45 min, all three together)

1. Lead states the target in one sentence: *one engine, every number traceable to source, weather cascades to covenant headroom.*
2. Whiteboard + lock the canonical schema and trace format (PRD §5).
3. Lead announces: the **3 systems** we reconcile, the **demo story** (PRD §10), and the **one operational pain** from the business-context doc the demo centers on.
4. Assign lanes (below).
5. Set sync rhythm + feature-freeze time (bottom of this doc).
6. Lead ships stub dataset before anyone leaves the table.

---

## Lane A — Foundation (data)

**Owns:** ingestion + reconciliation + GL mapping.

**Deliverables**
- One adapter per accounting system reading its export → canonical transaction records.
- Reconciliation: GL mapping collapses source accounts → canonical chart, tagging each txn with its `driver` and `mapping_rule_id`.
- LLM-assisted mapping: model suggests a mapping (confidence + rationale) → controller approves/rejects → decision logged. Validate suggestions against the provided mapping file; report agreement rate.

**Produces for the engine:** a clean table of canonical transaction records + a list of project/milestone records, conforming exactly to PRD §5.

**Definition of done:** 3 systems load into the canonical schema with zero schema violations; every txn has a `mapping_rule_id` traceable to a rule; LLM mapping demo runs with a logged approve/reject.

**Best fit:** whoever is strongest with messy CSV/Excel and data cleaning.

---

## Lane B — Engine (lead)

**Owns:** canonical schema + driver model + forecast + the traceability spine. This is the spine everyone plugs into and the integration point.

**Deliverables**
- The canonical schema as code (the contract Lane A fills and Lane C reads).
- Five-driver model (PRD §6), each independently tunable.
- 13-week forecast: net cash + running balance per week.
- Covenant headroom calc per the covenant doc rule.
- **Traceability spine:** every computed value carries trace metadata; expose a `trace(value)` path that returns driver → assumptions → toggle → contributing source records.

**Exposes to Lane C:** a single computed forecast object (per scenario) that both the forecast view and the dashboards read from. *Same object → no two numbers disagree.*

**Definition of done:** given canonical data + a scenario, returns a 13-week forecast where any cell can be traced end to end to source records.

**Note for the lead:** your job is the spine *and* keeping A and C unblocked. Don't disappear into engine code — timebox deep work, treat "is anyone stuck?" as higher priority than your own lane.

---

## Lane C — Experience (front + demo)

**Owns:** weather chain + scenario engine + covenant flagging + role views + demo + README.

**Deliverables**
- Weather → workable-days → schedule-slip logic feeding the engine's timing (uses Open-Meteo).
- Scenario engine: base / wet-quarter / dry-quarter, each perturbing only the weather input (PRD §7).
- Covenant traffic light (green/amber/red) reading engine output.
- Four role views as windows on the engine (CFO + Opco MD full; Board + Project Lead summary cards).
- The drill-down UI that walks the demo narrative (PRD §10).
- README + setup guide.

**Reads from the engine:** the computed forecast object + the `trace()` path. Builds nothing of its own truth — renders the engine's.

**Definition of done:** flipping a scenario visibly cascades to the covenant light; clicking any number drills to source via the engine's trace path; demo narrative runs without stutter.

**Best fit:** whoever pairs front-end with some quantitative sense (covenant + weather are modelling, not just UI). If a teammate has any finance background, they belong here.

---

## Phasing

- **Phase 0 (together):** lock schema + trace format, pick 3 systems, agree demo story, ship stub.
- **Phase 1 (parallel):** A builds real ingestion; B builds engine + trace against stub; C builds weather chain + scenarios + skeleton views against stub.
- **Phase 2 (integration):** stub → real reconciled data; views wire to engine; toggles cascade to covenant.
- **Phase 3 (polish):** covenant flagging, README, edge cases, rehearse the click-through.

## Cut list (cut from the bottom under time pressure)

Traceability drill-down → reconciliation/one-source-of-truth → weather cascade → GAAP/covenant correctness → role views → LLM mapping → ML coefficients / 4th-opco-as-config.

**Protect the traceability drill-down.** It's the highest-scoring feature and the first thing teams cut when panicking. Whoever finishes their lane first reinforces *that*, not UI polish.

## Rhythm & discipline

- **Sync:** 5-min "blocked / not blocked" heartbeat every few hours. Not a meeting.
- **Feature freeze:** at the last ~quarter of the clock, no new features — only integration, demo, README. Decided now, not argued about at 2am.
- **Never two people on UI.** One owns it; the other two stay on spine + data.

## Non-code deliverables (lead owns)

- **Demo narrative** — rehearsed out loud early; it *is* the product.
- **Submission framing** — README + pitch tell the "defensible, auditable forecast a CFO would open Monday" story, not "look at our dashboard."
