# Team Checklist — Altis Cash Flow Forecast
**Last updated:** 2026-06-06  
**Tests:** 14/14 passing ✅

---

## Lane A — Data (Samo)

### Done ✅
- [x] GL mapping file (`data/gl_mapping.csv`) — 11 rules, all systems covered
- [x] Gilde adapter (`ingest_gilde.py`) — Heeze GL files, 9,673 rows
- [x] Yuki adapter (`ingest_yuki.py`) — Peter Ummels files, 14,574 rows
- [x] Snelstart adapter (`ingest_snelstart.py`) — Winschoten + Company E, 12,647 rows
- [x] Merge script (`ingest_all.py`) — 36,894 rows, €122M, 0 errors
- [x] Debtor lookup table (`data/debtor_lookup.csv`) — 484 Trek codes extracted
- [x] Portfolio P&L JSON added to repo
- [x] Opco names corrected (Heeze, Winschoten, PeterUmmels, Andijk)
- [x] Review checklist (`data/lane_a_review_checklist.md`)

### Blocked / Out of scope ⛔
- [ ] Missing Heeze GL8000 files (2024/2025/2026) — not accessible
- [ ] Debtor lookup company names — team can't provide in time
- [ ] Cost data for Andijk, Peter Ummels, Heeze — not in dataset
- [ ] Project/WIP data — not provided (engine uses calibrated synthetic pipeline instead)
- [ ] Covenant document — not provided (engine uses industry-standard assumptions instead)

### Still needed ⚠️
- [ ] Fill in `data/lane_a_review_checklist.md` — sign off on LLM mapping decisions

---

## Lane B — Engine (Lead)

### Done ✅
- [x] Canonical schema (`engine/schema.py`)
- [x] Five-driver forecast model (`engine/forecast.py`)
- [x] Traceability spine — every cell traceable to source records
- [x] VAT remittance computation (`engine/vat.py`)
- [x] Three covenant metrics: min_liquidity, leverage, DSCR (`engine/covenant.py`)
- [x] EBITDA derivation from P&L JSON (`engine/ebitda.py`)
- [x] Payment-lag ML estimator (`engine/learn.py`)
- [x] Weather coefficient estimator (`engine/learn.py`)
- [x] Loader for real data (`engine/load.py`)
- [x] Synthetic pipeline calibrated to real opco revenue (`engine/pipeline.py`)
- [x] Config with all tunable assumptions (`engine/config.py`)
- [x] Stub dataset (`engine/stub.py`)
- [x] 14 tests all passing (`tests.py`)

### Still needed ⚠️
- [ ] Wire real `transactions.csv` into the app (swap stub → real data)
- [ ] Confirm `engine/pipeline.py` tuning — does base scenario dip to amber on real numbers?
- [ ] Verify covenant headroom numbers are defensible for the demo narrative

---

## Lane C — Experience (UI / Demo)

### Done ✅
- [x] Weather → workable days → schedule slip (`engine/weather.py`)
- [x] Base / wet-quarter / dry-quarter scenario engine
- [x] Streamlit app (`app.py`) — full UI built
- [x] Covenant traffic light (green / amber / red)
- [x] CFO view — 13-week forecast, driver breakdown, scenario toggles
- [x] Drill-down trace path wired to UI
- [x] Biggest movers (base → wet) surfaced in UI
- [x] Per-opco forecast breakdown
- [x] README updated

### Still needed ⚠️
- [ ] Rehearse the demo click-through (PRD §10) — run it out loud end to end
- [ ] Board + Project Lead summary cards (PRD scope item 6) — confirm in or cut
- [ ] Confirm the wet-quarter scenario visibly moves the covenant light in the demo

---

## Integration — Everyone

- [ ] Run `ingest_all.py` → feed real `transactions.csv` into the app → confirm numbers look right
- [ ] Run the full demo narrative (PRD §10) start to finish — no stutter
- [ ] README covers setup + one-line run command
- [ ] Confirm data deletion plan (licensed data, delete within 3 days of event)
