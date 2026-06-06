# Team Checklist — Actions Remaining
**Last updated:** 2026-06-06  
**Tests:** 14/14 passing ✅

---

## Lane A — Data
- [ ] Fill in `data/lane_a_review_checklist.md` — sign off on all LLM mapping decisions before submission

---

## Lane B — Engine
- [ ] Wire real `transactions.csv` into the app — swap stub for real data
- [ ] Confirm base scenario dips to amber on real numbers (tune `engine/pipeline.py` if needed)
- [ ] Verify covenant headroom numbers make sense for the demo narrative

---

## Lane C — UI / Demo
- [ ] Rehearse the full demo click-through (PRD §10) out loud, end to end
- [ ] Confirm wet-quarter scenario visibly moves the covenant light during the demo
- [ ] Decide: Board + Project Lead summary cards — build or cut?

---

## Everyone — Integration
- [ ] Run `ingest_all.py` → load into app → sanity check the numbers look right
- [ ] Run full demo narrative without stutter
- [ ] README has setup instructions + one-line run command
- [ ] Agree on data deletion plan (licensed data — delete within 3 days of event)
