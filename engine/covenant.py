"""Covenant calculation — ALL three common forms implemented and selected by
`cfg.covenant_metric`, so the missing covenant doc is a config flip, not a barrier.

PRD section 7: implement the threshold + calculation EXACTLY as the covenant doc
specifies. When it arrives:
  - if it's one of these three -> set covenant_metric + the numbers in config.py
  - if it's something bespoke -> add a branch in `headroom_metric` (one function)
Everything downstream (lights, views, traceability, tests) is untouched: it only
reads `headroom_metric`'s output, where >0 means safe and the magnitude is the
distance to breach in that metric's own units.
"""
from __future__ import annotations

from typing import List, Optional

from .config import ForecastConfig


def headroom_metric(running_balance: List[float], net_cash: List[float],
                    cfg: ForecastConfig) -> List[float]:
    """Headroom per week. >0 = safe; 0 = exactly at the covenant; <0 = breach.

    Units depend on the metric:
      min_liquidity -> EUR of cash above the floor
      leverage      -> turns of Net Debt/EBITDA below the cap
      dscr          -> ratio above the minimum coverage
    """
    m = cfg.covenant_metric
    if m == "min_liquidity":
        return [b - cfg.covenant_threshold for b in running_balance]

    if m == "leverage":
        # cash reduces net debt; lower leverage = safer. headroom = cap - actual.
        out = []
        for b in running_balance:
            net_debt = cfg.gross_debt - b
            leverage = net_debt / cfg.ttm_ebitda if cfg.ttm_ebitda else float("inf")
            out.append(cfg.max_leverage - leverage)
        return out

    if m == "dscr":
        # weekly slice of annual EBITDA & debt service; cash buffer helps coverage.
        weeks = max(1, len(running_balance))
        ebitda_w = cfg.ttm_ebitda / 52.0
        ds_w = cfg.annual_debt_service / 52.0
        out = []
        for b in running_balance:
            dscr = (ebitda_w + max(b, 0) / weeks) / ds_w if ds_w else float("inf")
            out.append(dscr - cfg.min_dscr)
        return out

    raise ValueError(f"unknown covenant_metric: {m!r}")


def amber_buffer(cfg: ForecastConfig) -> float:
    """How close to breach counts as amber, in the active metric's units."""
    return {
        "min_liquidity": cfg.covenant_amber_buffer,
        "leverage": 0.5,     # within half a turn of the cap
        "dscr": 0.15,        # within 0.15 of the minimum ratio
    }.get(cfg.covenant_metric, cfg.covenant_amber_buffer)


def lights(headroom: List[float], cfg: ForecastConfig) -> List[str]:
    buf = amber_buffer(cfg)
    out = []
    for h in headroom:
        if h < 0:
            out.append("red")
        elif h < buf:
            out.append("amber")
        else:
            out.append("green")
    return out


def first_breach_week(lights_seq: List[str]) -> Optional[int]:
    """Index of the first amber/red week, or None if green all the way.
    The Board's core question: 'are we safe before the meeting?'"""
    for i, l in enumerate(lights_seq):
        if l in ("amber", "red"):
            return i
    return None
