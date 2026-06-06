"""Legit, scoped ML (PRD section 6): estimate single INTERPRETABLE coefficients
that feed the drivers — never a black-box end-to-end forecast.

Two estimators:
  1. payment_lag per customer_segment   (days)   -> feeds config.payment_lag_days
  2. working_days_lost per mm rain / frost day    -> feeds the weather operator

Each returns an inspectable number with a fit summary (n, r2), so a controller
can see it, sanity-check it, and override it. That's the whole point: the model
*suggests* a coefficient, a human keeps authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import median
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np


@dataclass
class Coefficient:
    name: str
    value: float
    unit: str
    n: int
    r2: Optional[float] = None
    note: str = ""

    def __str__(self) -> str:
        r2 = f", r2={self.r2:.2f}" if self.r2 is not None else ""
        return f"{self.name} = {self.value:.3g} {self.unit} (n={self.n}{r2}) {self.note}"


# --- 1. payment lag per segment ------------------------------------------------

def estimate_payment_lag(
    pairs_by_segment: Dict[str, Sequence[Tuple[date, date]]],
    robust: bool = True,
) -> Dict[str, Coefficient]:
    """From matched (invoice_date, payment_date) pairs per segment, estimate the
    typical lag in days. `robust=True` uses the median (resists a few late payers).

    Lane A integration: build the pairs by matching open_ar invoices to the
    `actual` customer_payment that settles them (needs an invoice<->payment link).
    Drop the resulting dict straight into config.payment_lag_days.
    """
    out: Dict[str, Coefficient] = {}
    for seg, pairs in pairs_by_segment.items():
        lags = [(pay - inv).days for inv, pay in pairs if pay >= inv]
        if not lags:
            continue
        val = median(lags) if robust else sum(lags) / len(lags)
        out[seg] = Coefficient(
            name=f"payment_lag[{seg}]", value=float(val), unit="days",
            n=len(lags), note="(median)" if robust else "(mean)")
    return out


# --- 2. working days lost per mm rain / frost day ------------------------------

@dataclass
class WeatherObs:
    rain_mm: float
    frost_days: float
    working_days_lost: float


def estimate_weather_coeffs(obs: List[WeatherObs]) -> Dict[str, Coefficient]:
    """OLS: working_days_lost ~ b_rain * rain_mm + b_frost * frost_days.

    Returns one coefficient per predictor. These feed the weather operator: given
    a scenario's rain/frost, predict working_days_lost, which slips milestones.
    Lane C supplies the Open-Meteo series; this turns it into the slip number.
    """
    if len(obs) < 3:
        raise ValueError("need >=3 observations to fit weather coefficients")
    X = np.array([[o.rain_mm, o.frost_days] for o in obs], dtype=float)
    y = np.array([o.working_days_lost for o in obs], dtype=float)
    # least squares without intercept (no rain/frost -> no days lost)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ beta
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2)) or 1.0
    r2 = 1 - ss_res / ss_tot
    return {
        "rain": Coefficient("days_lost_per_mm_rain", float(beta[0]),
                            "days/mm", len(obs), r2),
        "frost": Coefficient("days_lost_per_frost_day", float(beta[1]),
                             "days/frost-day", len(obs), r2),
    }


def predict_days_lost(rain_mm: float, frost_days: float,
                      coeffs: Dict[str, Coefficient]) -> int:
    """Turn a scenario's weather into a working_days_lost slip (rounded)."""
    val = rain_mm * coeffs["rain"].value + frost_days * coeffs["frost"].value
    return max(0, round(val))
