"""Lane B spine: turn the unified table + projects + a scenario into a 13-week
forecast where every cell traces to source records.

Design rule: a cash event becomes a TracedValue the moment it is placed in a
week. Drivers, net cash, balance and covenant headroom are all aggregations of
TracedValues, so `trace()` is just a filter over them — drill-down for free.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional

from . import covenant as covenant_rule
from .config import ForecastConfig
from .schema import Project, TracedValue, Transaction
from .vat import compute_vat_remittances

# Weather handoff (Lane C owns producing this): working days lost per project,
# per scenario. base = no shift. Lane B owns *applying* it.
WeatherShift = Dict[str, int]   # {project_id: working_days_lost}

_DRIVER_ORDER = [
    "milestone_billing", "customer_payment", "materials",
    "subcontractor", "vat_remittance", "other",
]


@dataclass
class Forecast:
    scenario: str
    weeks: List[date]                                   # Monday of each week
    opening_balance: float
    cfg: ForecastConfig
    contributions: List[TracedValue] = field(default_factory=list)
    opco: str = "PORTFOLIO"                             # scope of this forecast

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

    def covenant_headroom(self) -> List[float]:
        return covenant_rule.headroom_metric(
            self.running_balance(), self.net_cash(), self.cfg)

    def covenant_lights(self) -> List[str]:
        return covenant_rule.lights(self.covenant_headroom(), self.cfg)

    def trace(self, week: int, driver: Optional[str] = None) -> List[TracedValue]:
        """The drill-down path: every TracedValue behind a cell."""
        return [
            c for c in self.contributions
            if c.week == week and (driver is None or c.driver == driver)
        ]

    def to_dict(self) -> dict:
        """One serialisable object Lane C reads (even across a process / JS boundary).
        Same object -> no two numbers disagree."""
        return {
            "opco": self.opco,
            "scenario": self.scenario,
            "weeks": [w.isoformat() for w in self.weeks],
            "opening_balance": self.opening_balance,
            "drivers": self.drivers(),
            "net_cash": self.net_cash(),
            "running_balance": self.running_balance(),
            "covenant_headroom": self.covenant_headroom(),
            "covenant_lights": self.covenant_lights(),
            "first_breach_week": covenant_rule.first_breach_week(self.covenant_lights()),
            "contributions": [asdict(c) for c in self.contributions],
        }


def _week_index(d: date, anchor: date, horizon: int) -> Optional[int]:
    w = (d - anchor).days // 7
    return w if 0 <= w < horizon else None


def _outflow_driver(driver_type: str) -> str:
    if driver_type in ("materials", "subcontractor", "vat_remittance"):
        return driver_type
    return "other"


def build_forecast(
    transactions: List[Transaction],
    projects: List[Project],
    scenario: str = "base",
    cfg: Optional[ForecastConfig] = None,
    weather_shift: Optional[WeatherShift] = None,
    opco: Optional[str] = None,
) -> Forecast:
    """Build a 13-week forecast. Pass `opco` to scope to one operating company
    (for per-opco views); omit it for the consolidated portfolio."""
    cfg = cfg or ForecastConfig()
    weather_shift = weather_shift or {}
    weeks = [cfg.anchor_monday + timedelta(weeks=w) for w in range(cfg.horizon_weeks)]

    all_opcos = sorted({t.opco for t in transactions if t.opco})
    rows = [t for t in transactions if opco is None or t.opco == opco]
    opening = cfg.opening_for(opco, all_opcos)
    fc = Forecast(scenario=scenario, weeks=weeks, opening_balance=opening, cfg=cfg)
    fc.opco = opco or "PORTFOLIO"

    # Compute quarterly BTW remittance from the vat column unless Lane A already
    # supplied explicit vat_remittance rows. Decide from the FULL dataset (not the
    # per-opco slice) so consolidated and per-opco forecasts stay reconciled.
    has_explicit_vat = any(t.driver_type == "vat_remittance" for t in transactions)
    if cfg.compute_vat and not has_explicit_vat:
        rows = rows + compute_vat_remittances(rows, opco_label=opco or "PORTFOLIO")

    weather_exposed = {p.project_id for p in projects if p.weather_exposure > 0}

    for t in rows:
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
            seg = t.counterparty_segment or cfg.segment_for(t.counterparty)
            lag = cfg.lag_for(seg)
            cash_date = eff_date + timedelta(days=lag)
            assumptions.append(f"payment_lag={lag}d({seg})")
            driver = "customer_payment"
            value = t.amount_incl_vat
            comp = f"open_ar gross {value:,.0f} @ invoice+{lag}d"
        elif t.status == "open_ap":
            cash_date = eff_date
            driver = _outflow_driver(t.driver_type)
            value = t.amount_incl_vat
            comp = f"open_ap {driver} {value:,.0f} due"
        elif t.status == "wip":
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
            toggle_values={"weather_shift": dict(weather_shift)},
            computation=comp,
        ))

    # --- committed outflows from the project schedules (PRD section 6, drivers
    # 1-2). The real GL is revenue-only, so materials/subcontractor cash comes
    # from here. Materials are locked (no weather slip); subcontractor is tied to
    # milestones (slips with weather) -> this is what creates the squeeze.
    for p in projects:
        if opco is not None and p.opco != opco:
            continue
        exposed = p.weather_exposure > 0
        _add_schedule(fc, p, p.materials_schedule, "materials",
                      movable=False, exposed=exposed, weather_shift=weather_shift,
                      scenario=scenario, cfg=cfg)
        _add_schedule(fc, p, p.subcontractor_schedule, "subcontractor",
                      movable=True, exposed=exposed, weather_shift=weather_shift,
                      scenario=scenario, cfg=cfg)

    return fc


def _add_schedule(fc, project, schedule, driver, movable, exposed,
                  weather_shift, scenario, cfg):
    for i, s in enumerate(schedule):
        eff_date = s.date
        assumptions: List[str] = []
        slip = weather_shift.get(project.project_id, 0) if (movable and exposed) else 0
        if slip:
            eff_date = eff_date + timedelta(days=slip)
            assumptions.append(f"weather_slip=+{slip}d")
        week = _week_index(eff_date, cfg.anchor_monday, cfg.horizon_weeks)
        if week is None:
            continue
        fc.contributions.append(TracedValue(
            value=-abs(s.amount), week=week, driver=driver,
            contributing_records=[f"sched:{project.project_id}:{driver}:{i}"],
            assumptions_applied=assumptions,
            scenario=scenario,
            toggle_values={"weather_shift": dict(weather_shift)},
            computation=f"{driver} schedule {-abs(s.amount):,.0f} ({project.project_id})",
        ))


def build_all_opcos(
    transactions: List[Transaction],
    projects: List[Project],
    scenario: str = "base",
    cfg: Optional[ForecastConfig] = None,
    weather_shift: Optional[WeatherShift] = None,
) -> Dict[str, Forecast]:
    """Consolidated + one forecast per opco, all from the same engine.

    Returns {"PORTFOLIO": consolidated, "<opco>": per-opco, ...}. This is what the
    role views read: Board/CFO use PORTFOLIO, Opco MD uses its own opco — and
    because every view is this same engine, no two numbers disagree.
    """
    cfg = cfg or ForecastConfig()
    opcos = sorted({t.opco for t in transactions if t.opco})
    out: Dict[str, Forecast] = {
        "PORTFOLIO": build_forecast(transactions, projects, scenario, cfg, weather_shift),
    }
    for o in opcos:
        out[o] = build_forecast(transactions, projects, scenario, cfg, weather_shift, opco=o)
    return out


@dataclass
class Mover:
    week: int
    driver: str
    base_value: float
    scenario_value: float

    @property
    def delta(self) -> float:
        return self.scenario_value - self.base_value


def biggest_movers(base: Forecast, scenario: Forecast, top: int = 5) -> List[Mover]:
    """What changed most between base and a scenario, per (week, driver).
    Powers the demo: 'click the week-9 dip -> biggest mover is deferred billing'."""
    bd, sd = base.drivers(), scenario.drivers()
    movers: List[Mover] = []
    for driver in set(bd) | set(sd):
        bv = bd.get(driver, [0.0] * len(base.weeks))
        sv = sd.get(driver, [0.0] * len(scenario.weeks))
        for w in range(min(len(bv), len(sv))):
            if abs(sv[w] - bv[w]) > 0.5:
                movers.append(Mover(w, driver, bv[w], sv[w]))
    movers.sort(key=lambda m: abs(m.delta), reverse=True)
    return movers[:top]
