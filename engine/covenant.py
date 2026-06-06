"""Covenant calculation — ISOLATED so the real rule drops into ONE place.

PRD section 7: implement the threshold + calculation EXACTLY as the covenant doc
specifies. We don't have that doc yet, so this is a clearly-marked placeholder.
When it arrives, replace `headroom_metric` only; everything downstream (lights,
views, traceability) keeps working unchanged.
"""
from __future__ import annotations

from typing import List

from .config import ForecastConfig


def headroom_metric(running_balance: List[float], net_cash: List[float],
                    cfg: ForecastConfig) -> List[float]:
    """Headroom per week = (covenant metric) - threshold.

    >>> REPLACE THIS BODY WHEN THE COVENANT DOC ARRIVES <<<

    Placeholder rule: minimum-liquidity covenant — the portfolio must keep cash
    above `covenant_threshold`. Headroom = running cash balance - threshold.

    Common real alternatives (selectable later via cfg.covenant_metric):
      - net-debt / EBITDA leverage ratio vs a max multiple
      - DSCR (debt service coverage) vs a min ratio
      - minimum 13-week liquidity buffer (this placeholder)
    """
    return [b - cfg.covenant_threshold for b in running_balance]


def lights(headroom: List[float], cfg: ForecastConfig) -> List[str]:
    out = []
    for h in headroom:
        if h < 0:
            out.append("red")
        elif h < cfg.covenant_amber_buffer:
            out.append("amber")
        else:
            out.append("green")
    return out


def first_breach_week(lights_seq: List[str]) -> int | None:
    """Index of the first amber/red week, or None if green all the way.
    The Board's core question: 'are we safe before the meeting?'"""
    for i, l in enumerate(lights_seq):
        if l in ("amber", "red"):
            return i
    return None
