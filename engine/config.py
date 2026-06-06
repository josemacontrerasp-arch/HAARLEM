"""Tunable assumptions for the engine. Every number here is inspectable and
overridable (PRD: drivers are independently tunable; ML only ever produces one
of these interpretable coefficients, never a black-box forecast)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict


@dataclass
class ForecastConfig:
    # Week 0 starts on this Monday. The 13-week horizon is anchor .. anchor+13w.
    anchor_monday: date = date(2026, 6, 1)
    horizon_weeks: int = 13

    # Opening bank position (sum of actuals already settled before the anchor).
    # Lane A's real `actual` rows can replace this; stubbed for now.
    opening_balance: float = 250_000.0

    # Payment lag in DAYS by customer_segment. open_ar settles at date + lag.
    # GAP: segment isn't in the unified table yet -> resolved via counterparty_map.
    # These are exactly the coefficients the "legit ML" step can estimate.
    payment_lag_days: Dict[str, int] = field(default_factory=lambda: {
        "government": 45,
        "enterprise": 30,
        "sme": 21,
        "default": 30,
    })

    # Temporary counterparty -> segment lookup until Lane A ships the column.
    counterparty_segment: Dict[str, str] = field(default_factory=lambda: {
        "Gemeente": "government",   # Dutch municipalities -> government, slow payers
        "Bouwbedrijf": "enterprise",
    })

    # Covenant rule. PRD section 7: implement EXACTLY as the covenant doc says.
    # We don't have that doc yet, so this is a clearly-marked placeholder behind
    # config -> swap the real metric + threshold in one place when it arrives.
    covenant_threshold: float = 100_000.0   # min headroom metric (EUR) before breach
    covenant_amber_buffer: float = 50_000.0  # within this of threshold -> amber

    def segment_for(self, counterparty: str | None) -> str:
        if not counterparty:
            return "default"
        for key, seg in self.counterparty_segment.items():
            if key.lower() in counterparty.lower():
                return seg
        return "default"

    def lag_for(self, segment: str) -> int:
        return self.payment_lag_days.get(segment, self.payment_lag_days["default"])
