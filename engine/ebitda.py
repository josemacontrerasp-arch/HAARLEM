"""Derive TTM EBITDA from the portfolio P&L — the EBITDA input for the leverage
covenant (Net Debt / EBITDA, trailing-12-month).

Reality of the data: only ONE opco (Winschoten) has cost data. The others are
revenue-only. So we compute a TRUE EBITDA where costs exist and a MARGIN-ESTIMATE
elsewhere (using Winschoten's EBITDA margin), and we label which is which. Every
number stays inspectable and overridable — same principle as engine/learn.py.

Output feeds config.ttm_ebitda for the covenant. Pass the P&L JSON path (the file
is gitignored licensed data, kept out of the repo).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

_DUTCH_MONTHS = {"jan": 1, "feb": 2, "mrt": 3, "apr": 4, "mei": 5, "jun": 6,
                 "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dec": 12}


def _key_to_ym(key: str) -> Optional[Tuple[int, int]]:
    try:
        mon, yy = key.split("-")
        return (2000 + int(yy), _DUTCH_MONTHS[mon.lower()])
    except (ValueError, KeyError):
        return None


def _collect_revenue(opco: dict) -> Dict[Tuple[int, int], float]:
    """Sum every revenue-ish series in an opco block into one month -> amount map.
    Opcos store revenue under 'revenue' or several 'revenue_YYYY*' / partial keys."""
    out: Dict[Tuple[int, int], float] = {}
    for k, v in opco.items():
        if not isinstance(v, dict):
            continue
        if k == "costs" or "cost" in k:
            continue
        if k == "revenue" or k.startswith("revenue"):
            for mk, amt in v.items():
                ym = _key_to_ym(mk)
                if ym and isinstance(amt, (int, float)):
                    out[ym] = out.get(ym, 0.0) + float(amt)
    return out


def _collect_costs(opco: dict) -> Dict[Tuple[int, int], float]:
    costs = opco.get("costs")
    out: Dict[Tuple[int, int], float] = {}
    if isinstance(costs, dict):
        for mk, amt in costs.items():
            ym = _key_to_ym(mk)
            if ym and isinstance(amt, (int, float)):
                out[ym] = out.get(ym, 0.0) + float(amt)
    return out


def _ttm(series: Dict[Tuple[int, int], float], months: int = 12) -> float:
    if not series:
        return 0.0
    last12 = sorted(series)[-months:]
    return sum(series[ym] for ym in last12)


@dataclass
class OpcoEbitda:
    opco: str
    ttm_revenue: float
    ttm_costs: Optional[float]
    ttm_ebitda: float
    method: str   # "actual" | "margin-estimate" | "none"


@dataclass
class PortfolioEbitda:
    by_opco: List[OpcoEbitda] = field(default_factory=list)
    margin_used: float = 0.0
    margin_source: str = ""

    @property
    def total_ttm_ebitda(self) -> float:
        return round(sum(o.ttm_ebitda for o in self.by_opco), 2)

    @property
    def total_ttm_revenue(self) -> float:
        return round(sum(o.ttm_revenue for o in self.by_opco), 2)

    @property
    def margin_plausible(self) -> bool:
        """Construction/roofing EBITDA margins are typically ~5-20%. A margin far
        above that means the cost data is incomplete -> EBITDA is NOT defensible."""
        return 0.0 < self.margin_used <= 0.25

    def warnings(self) -> List[str]:
        w = []
        if not self.margin_plausible:
            w.append(f"EBITDA margin {self.margin_used:.0%} is implausible for roofing "
                     f"(~5-20% expected) -> cost data from '{self.margin_source}' is "
                     f"likely incomplete; portfolio EBITDA is NOT covenant-grade yet.")
        estimated = [o.opco for o in self.by_opco if o.method == "margin-estimate"]
        if estimated:
            w.append(f"EBITDA margin-estimated (no costs) for: {', '.join(estimated)}.")
        return w


def compute_portfolio_ebitda(pl_path: str, months: int = 12) -> PortfolioEbitda:
    with open(pl_path, encoding="utf-8") as fh:
        data = json.load(fh)

    opcos = {k: v for k, v in data.items()
             if isinstance(v, dict) and k != "metadata"}

    # 1) true EBITDA + margin from any opco that has costs (Winschoten).
    margin, margin_src = None, ""
    for name, blk in opcos.items():
        rev, cost = _collect_revenue(blk), _collect_costs(blk)
        if cost:
            r, c = _ttm(rev, months), _ttm(cost, months)
            if r > 0:
                margin, margin_src = (r - c) / r, name
                break

    result = PortfolioEbitda(margin_used=round(margin or 0.0, 4), margin_source=margin_src or "none")

    # 2) per-opco: actual where costs exist, else margin-estimate.
    for name, blk in opcos.items():
        rev = _collect_revenue(blk)
        cost = _collect_costs(blk)
        ttm_rev = round(_ttm(rev, months), 2)
        if cost:
            ttm_cost = round(_ttm(cost, months), 2)
            result.by_opco.append(OpcoEbitda(
                name, ttm_rev, ttm_cost, round(ttm_rev - ttm_cost, 2), "actual"))
        elif ttm_rev > 0 and margin is not None:
            result.by_opco.append(OpcoEbitda(
                name, ttm_rev, None, round(ttm_rev * margin, 2), "margin-estimate"))
        else:
            result.by_opco.append(OpcoEbitda(name, ttm_rev, None, 0.0, "none"))

    return result
