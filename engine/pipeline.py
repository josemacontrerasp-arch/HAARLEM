"""Forward project & WIP pipeline — reconstructed from real revenue.

No dedicated Project & WIP file was provided, and the reconciled GL is invoiced
receivables + history only (no WIP, no AP, no project schedules) — so weather has
nothing to act on. The brief allows "real OR realistic data", so we build a
forward pipeline CALIBRATED to each opco's true revenue run-rate from the P&L,
with documented industry ratios for the cost side. This is clearly synthetic-but-
grounded: real scale, real opco names, defensible assumptions.

Ratios (documented, overridable):
  - 13-week billing per opco  ≈ 3 x trailing monthly revenue (the horizon ~ a quarter)
  - materials      ≈ 40% of project value, ordered ~3 weeks before the milestone
  - subcontractor  ≈ 25% of project value, paid the week of the milestone
  - weather_exposure spread 0.3..0.9 (roofing is weather-exposed)
Each project bills as WIP (not yet invoiced) so weather can slip it — that is what
drives the cascade on real-scale numbers.
"""
from __future__ import annotations

import random
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

from .config import ForecastConfig
from .ebitda import _collect_revenue, _ttm
from .schema import Milestone, Project, Scheduled, Transaction

OPCO_DISPLAY = {
    "winschoten": "Winschoten", "andijk": "Andijk",
    "peter_ummels": "Brunssum", "heeze": "Heeze",
}
SEGMENTS = ["government", "enterprise", "sme"]

MATERIALS_RATIO = 0.40
SUBCONTRACTOR_RATIO = 0.25


def _monthly_revenue(blk: dict, months: int = 6) -> float:
    rev = _collect_revenue(blk)
    if not rev:
        return 0.0
    last = sorted(rev)[-months:]
    return sum(rev[ym] for ym in last) / max(1, len(last))


def build_pipeline(
    pl_path: str,
    cfg: Optional[ForecastConfig] = None,
    projects_per_opco: int = 4,
    seed: int = 42,
    min_monthly_revenue: float = 50_000.0,
) -> Tuple[List[Project], List[Transaction]]:
    """Return (projects, wip_transactions) calibrated to real opco revenue.

    wip_transactions are status='wip' milestone-billing rows the engine turns into
    weather-slippable future inflows; projects carry the materials/subcontractor
    schedules (outflows). Deterministic for a given seed.
    """
    import json
    cfg = cfg or ForecastConfig()
    rng = random.Random(seed)
    with open(pl_path, encoding="utf-8") as fh:
        data = json.load(fh)
    opcos = {k: v for k, v in data.items() if isinstance(v, dict) and k != "metadata"}

    projects: List[Project] = []
    wip_txns: List[Transaction] = []
    horizon = cfg.horizon_weeks

    for key, blk in opcos.items():
        opco = OPCO_DISPLAY.get(key, key)
        monthly = _monthly_revenue(blk)
        if monthly < min_monthly_revenue:
            continue  # skip opcos with no reliable revenue (e.g. Heeze partial)
        # forward book in the 13-week window: billable WIP in flight, as a multiple
        # of monthly revenue (cfg-tunable). Tuned so base dips to amber and weather
        # pushes it into the red.
        target = monthly * cfg.pipeline_revenue_multiple

        # split target into N projects with varied weights
        weights = [rng.uniform(0.6, 1.4) for _ in range(projects_per_opco)]
        wsum = sum(weights)
        for i, w in enumerate(weights):
            value = round(target * w / wsum, 2)
            pid = f"{opco[:3].upper()}-{i+1:02d}"
            exposure = round(rng.uniform(0.3, 0.9), 2)
            seg = rng.choice(SEGMENTS)
            # keep milestones early enough that collections (milestone + lag)
            # land inside the 13-week horizon, not beyond it
            mile_week = rng.randint(2, min(7, max(2, horizon - 3)))
            mile_date = cfg.anchor_monday + timedelta(weeks=mile_week)

            # cost schedule (outflows)
            mat_week = max(0, mile_week - 3)
            mat = [Scheduled(cfg.anchor_monday + timedelta(weeks=mat_week),
                             round(value * MATERIALS_RATIO, 2))]
            sub = [Scheduled(mile_date, round(value * SUBCONTRACTOR_RATIO, 2), f"{pid}-M1")]

            projects.append(Project(
                project_id=pid, opco=opco, customer=f"{opco} klant {i+1}",
                customer_segment=seg, contract_value=value,
                wip_to_date=round(value * 0.4, 2), percent_complete=0.4,
                weather_exposure=exposure,
                milestones=[Milestone(f"{pid}-M1", "Termijn dakwerk", mile_date,
                                      value, status="pending", weather_dependent=True)],
                materials_schedule=mat, subcontractor_schedule=sub))

            # the billing as WIP -> weather-slippable future inflow
            wip_txns.append(Transaction(
                record_id=f"wip:{pid}", source_system="gilde",
                source_file="(pipeline)", source_row=i, opco=opco,
                date=mile_date, gl_account_native="9000", gl_account_unified="1310",
                driver_type="milestone_billing", amount_excl_vat=value,
                vat_amount=0.0, amount_incl_vat=value, counterparty=f"{opco} klant {i+1}",
                project_id=pid, status="wip", description="WIP milestone (pipeline)",
                counterparty_segment=seg))

    return projects, wip_txns
