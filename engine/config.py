"""Tunable assumptions for the engine. Every number here is inspectable and
overridable (PRD: drivers are independently tunable; ML only ever produces one
of these interpretable coefficients, never a black-box forecast)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Optional


@dataclass
class ForecastConfig:
    # Week 0 starts on this Monday. The 13-week horizon is anchor .. anchor+13w.
    anchor_monday: date = date(2026, 6, 1)
    horizon_weeks: int = 13

    # Opening bank position (sum of actuals already settled before the anchor).
    # Lane A's real `actual` rows can replace this; stubbed for now.
    opening_balance: float = 250_000.0
    # Per-opco opening balances (for per-opco views). Falls back to an even split
    # of opening_balance across opcos seen in the data when empty.
    opening_balance_by_opco: Dict[str, float] = field(default_factory=dict)

    # If Lane A doesn't emit explicit vat_remittance rows, compute quarterly BTW
    # from the vat_amount column (engine/vat.py).
    compute_vat: bool = True

    # No bank/cash export was provided, so opening cash is assumed as this many
    # months of revenue (documented assumption used by load_full_state).
    opening_cash_months: float = 1.0

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

    # --- Covenant -----------------------------------------------------------
    # PRD section 7: implement EXACTLY as the covenant doc says. We don't have it
    # yet, so all THREE common forms are implemented (engine/covenant.py) and
    # selected here. When the doc lands, set covenant_metric + the right numbers
    # and nothing else changes.
    #
    # Per the lender's terms (told to us verbally, no doc yet): the covenant is
    # NET DEBT / EBITDA, EBITDA on a TRAILING-12-MONTH basis, TESTED QUARTERLY.
    # -> covenant_metric = "leverage", covenant_test_cadence = "quarterly".
    # STILL MISSING (the numbers): the loan/debt amount and the max multiple.
    covenant_metric: str = "leverage"        # min_liquidity | leverage | dscr
    covenant_test_cadence: str = "quarterly"  # quarterly | weekly

    # min_liquidity: cash must stay >= threshold (EUR)
    covenant_threshold: float = 100_000.0
    covenant_amber_buffer: float = 50_000.0  # within this of breach -> amber (metric units)

    # leverage: Net Debt / EBITDA must stay <= max_leverage (turns).
    # No covenant terms, cost data, or debt figures were provided, so we use
    # DOCUMENTED INDUSTRY-STANDARD ASSUMPTIONS (all overridable). See README.
    ebitda_assumed_margin: float = 0.10      # roofing/construction EBITDA ~8-15%
    assumed_entry_leverage: float = 3.0      # typical PE-buyout entry Net Debt/EBITDA
    gross_debt: float = 4_000_000.0          # derived from EBITDA x entry leverage
    ttm_ebitda: float = 1_500_000.0          # derived from P&L revenue x assumed margin
    max_leverage: float = 3.5                # typical mid-market leverage covenant cap

    # dscr: (cash + EBITDA) / debt_service must stay >= min_dscr (ratio)
    annual_debt_service: float = 600_000.0
    min_dscr: float = 1.25

    def segment_for(self, counterparty: Optional[str]) -> str:
        if not counterparty:
            return "default"
        for key, seg in self.counterparty_segment.items():
            if key.lower() in counterparty.lower():
                return seg
        return "default"

    def lag_for(self, segment: str) -> int:
        return self.payment_lag_days.get(segment, self.payment_lag_days["default"])

    def opening_for(self, opco: Optional[str], all_opcos: Optional[list] = None) -> float:
        if opco is None:
            return self.opening_balance
        if opco in self.opening_balance_by_opco:
            return self.opening_balance_by_opco[opco]
        if all_opcos:
            return self.opening_balance / max(1, len(all_opcos))
        return self.opening_balance
