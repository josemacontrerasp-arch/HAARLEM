"""Lane B spine: turn the unified table + projects + a scenario into a 13-week
forecast where every cell traces to source records.

Design rule: a cash event becomes a TracedValue the moment it is placed in a
week. Drivers, net cash, balance and covenant headroom are all aggregations of
TracedValues, so `trace()` is just a filter over them — drill-down for free.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional

from .config import ForecastConfig
from .schema import Project, TracedValue, Transaction

# Weather handoff (Lane C owns producing this): working days lost per project,
# per scenario. base = no shift. Lane B owns *applying* it.
WeatherShift = Dict[str, int]   # {project_id: working_days_lost}


@dataclass
class Forecast:
    scenario: str
    weeks: List[date]                                   # Monday of each week
    opening_balance: float
    contributions: List[TracedValue] = field(default_factory=list)

    # ---- aggregations (all derived from `contributions`) ----
    def drivers(self) -> Dict[str, List[float]]:
        out = {d: [0.0] * len(self.weeks) for d in _DRIVER_ORDER}
        for c in self.contributions:
            out.setdefault(c.driver, [0.0] * len(self.weeks))
            out[c.driver][c.week] += c.value
        return out

    def net_cash(self) -> List[float]:
        net = [0.0] * len(self.weeks)
        for c in self.contributions:
            net[c.week] += c.value
        return net

    def running_balance(self) -> List[float]:
        bal, run = [], self.opening_balance
        for n in self.net_cash():
            run += n
            bal.append(run)
        return bal

    def covenant_headroom(self, cfg: ForecastConfig) -> List[float]:
        # Placeholder rule until the covenant doc lands: headroom = balance - threshold.
        return [b - cfg.covenant_threshold for b in self.running_balance()]

    def covenant_lights(self, cfg: ForecastConfig) -> List[str]:
        lights = []
        for h in self.covenant_headroom(cfg):
            if h < 0:
                lights.append("red")
            elif h < cfg.covenant_amber_buffer:
                lights.append("amber")
            else:
                lights.append("green")
        return lights

    def trace(self, week: int, driver: Optional[str] = None) -> List[TracedValue]:
        """The drill-down path: every TracedValue behind a cell."""
        return [
            c for c in self.contributions
            if c.week == week and (driver is None or c.driver == driver)
        ]


_DRIVER_ORDER = [
    "milestone_billing", "customer_payment", "materials",
    "subcontractor", "vat_remittance", "other",
]


def _week_index(d: date, anchor: date, horizon: int) -> Optional[int]:
    w = (d - anchor).days // 7
    return w if 0 <= w < horizon else None


def build_forecast(
    transactions: List[Transaction],
    projects: List[Project],
    scenario: str = "base",
    cfg: Optional[ForecastConfig] = None,
    weather_shift: Optional[WeatherShift] = None,
) -> Forecast:
    cfg = cfg or ForecastConfig()
    weather_shift = weather_shift or {}
    weeks = [cfg.anchor_monday + timedelta(weeks=w) for w in range(cfg.horizon_weeks)]
    fc = Forecast(scenario=scenario, weeks=weeks, opening_balance=cfg.opening_balance)

    weather_exposed = {p.project_id for p in projects if p.weather_exposure > 0}

    for t in transactions:
        if t.status == "actual":
            continue  # already in opening_balance; not a forward cash event

        # --- weather operator: shift the event's date right by days lost -------
        # Only the revenue side moves: milestone billing / collections (open_ar,
        # wip) and milestone-tied subcontractor. Committed *materials* deliveries
        # are already locked -> they stay put. That gap IS the cash squeeze the
        # demo lands on (PRD section 10: "materials already paid despite billing slip").
        eff_date = t.date
        assumptions: List[str] = []
        weather_movable = t.status in ("open_ar", "wip") or t.driver_type == "subcontractor"
        slip = (weather_shift.get(t.project_id or "", 0)
                if (t.project_id in weather_exposed and weather_movable) else 0)
        if slip:
            eff_date = eff_date + timedelta(days=slip)
            assumptions.append(f"weather_slip=+{slip}d")

        # --- place the event in a week and sign it -----------------------------
        if t.status == "open_ar":
            # invoice issued, unpaid -> inflow at invoice_date + payment_lag
            seg = t.counterparty_segment or cfg.segment_for(t.counterparty)
            lag = cfg.lag_for(seg)
            cash_date = eff_date + timedelta(days=lag)
            assumptions.append(f"payment_lag={lag}d({seg})")
            driver = "customer_payment"
            value = t.amount_incl_vat
            comp = f"open_ar gross {value:,.0f} @ invoice+{lag}d"
        elif t.status == "open_ap":
            # committed outflow due on its date (materials / subcontractor)
            cash_date = eff_date
            driver = t.driver_type if t.driver_type in ("materials", "subcontractor") else "other"
            value = t.amount_incl_vat
            comp = f"open_ap {driver} {value:,.0f} due"
        elif t.status == "wip":
            # work done, not yet invoiced -> bill at date, collect after lag
            seg = t.counterparty_segment or cfg.segment_for(t.counterparty)
            lag = cfg.lag_for(seg)
            cash_date = eff_date + timedelta(days=lag)
            assumptions.append(f"wip->bill, payment_lag={lag}d({seg})")
            driver = "milestone_billing"
            value = abs(t.amount_incl_vat)   # WIP becomes a receivable (inflow)
            comp = f"wip {value:,.0f} -> milestone bill @ +{lag}d"
        else:
            continue

        week = _week_index(cash_date, cfg.anchor_monday, cfg.horizon_weeks)
        if week is None:
            continue

        fc.contributions.append(TracedValue(
            value=value, week=week, driver=driver,
            contributing_records=[t.record_id],
            assumptions_applied=assumptions,
            scenario=scenario,
            toggle_values={"weather_shift": weather_shift},
            computation=comp,
        ))

    return fc
