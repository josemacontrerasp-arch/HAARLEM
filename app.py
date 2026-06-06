from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import streamlit as st

from engine import (
    Forecast,
    ForecastConfig,
    Project,
    Transaction,
    biggest_movers,
    build_forecast,
    covenant,
    make_stub,
)
from engine.forecast import build_all_opcos
from engine.load import load_projects, load_transactions


ScenarioConfig = Tuple[str, str]

SCENARIOS: Dict[str, ScenarioConfig] = {
    "Base": (
        "base",
        "No weather adjustment. This is the baseline 13-week cash forecast.",
    ),
    "Wet Quarter": (
        "wet-quarter",
        "Weather-exposed projects lose working days, pushing billing and collections later.",
    ),
    "Dry Quarter": (
        "dry-quarter",
        "Weather-exposed projects regain working days, pulling some billing and collections earlier.",
    ),
}

DRIVER_LABELS = {
    "milestone_billing": "Milestone billing",
    "customer_payment": "Customer payment",
    "materials": "Materials",
    "subcontractor": "Subcontractor",
    "vat_remittance": "VAT remittance",
    "other": "Other",
}

LIGHT_COLORS = {
    "green": ("#166534", "#dcfce7", "#bbf7d0"),
    "amber": ("#92400e", "#fef3c7", "#fde68a"),
    "red": ("#991b1b", "#fee2e2", "#fecaca"),
}

TRANSACTION_SUFFIXES = {".csv", ".parquet", ".duckdb", ".db", ".sqlite"}
PROJECT_SUFFIXES = {".json"}


@dataclass
class DashboardState:
    cfg: ForecastConfig
    transactions: List[Transaction]
    projects: List[Project]
    forecasts: Dict[str, Forecast]
    opco_forecasts: Dict[str, Dict[str, Forecast]] = field(default_factory=dict)
    weather_shifts: Dict[str, Dict[str, int]] = field(default_factory=dict)
    data_label: str = "Demo stub data"
    data_note: str = ""
    transaction_summary: Optional[Dict[str, object]] = None
    build_notes: List[str] = field(default_factory=list)
    using_stub: bool = True


def format_eur(value: float) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}EUR {abs(value):,.0f}"


def format_days(days: int) -> str:
    if days > 0:
        return f"+{days} days"
    if days < 0:
        return f"{days} days"
    return "0 days"


def format_shift(weather_shift: Dict[str, int]) -> str:
    if not weather_shift:
        return "none"
    return ", ".join(f"{project}: {days:+d}d" for project, days in weather_shift.items())


def weather_exposed_projects(projects: List[Project]) -> List[Project]:
    return [project for project in projects if project.weather_exposure > 0]


def weather_shift_days(project: Project, scenario: str) -> int:
    exposure = max(0.0, min(float(project.weather_exposure), 1.0))
    if scenario == "wet-quarter":
        return max(1, round(35 * exposure))
    if scenario == "dry-quarter":
        return min(-1, -round(14 * exposure))
    return 0


def build_weather_shift(projects: List[Project], scenario: str) -> Dict[str, int]:
    if scenario == "base":
        return {}

    weather_shift: Dict[str, int] = {}
    for project in weather_exposed_projects(projects):
        days = weather_shift_days(project, scenario)
        if days != 0:
            weather_shift[project.project_id] = days
    return weather_shift


def discover_files(suffixes: set[str]) -> List[str]:
    base = Path.cwd()
    out: List[str] = []
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {".git", "__pycache__"} for part in path.parts):
            continue
        if path.suffix.lower() in suffixes:
            out.append(path.relative_to(base).as_posix())
    return sorted(out)


def resolve_data_path(raw_path: str, label: str) -> str:
    cleaned = raw_path.strip()
    if not cleaned:
        raise FileNotFoundError(f"{label} path is empty")

    path = Path(cleaned).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        raise FileNotFoundError(f"{label} file not found: {path}")
    return str(path)


def sidebar_path_picker(label: str, suffixes: set[str], key: str, prefer: str = "") -> str:
    options = [""] + discover_files(suffixes)
    default_index = 0
    if prefer:
        for i, opt in enumerate(options):
            if prefer.lower() in opt.lower():
                default_index = i
                break
    selected = st.sidebar.selectbox(
        f"Select {label}", options, index=default_index, key=f"{key}_select")
    manual = st.sidebar.text_input(
        f"{label} path",
        placeholder="Enter a relative or absolute path",
        key=f"{key}_input",
    )
    return manual.strip() or selected


def build_forecast_bundle(
    transactions: List[Transaction],
    projects: List[Project],
    cfg: ForecastConfig,
) -> Tuple[
    Dict[str, Forecast],
    Dict[str, Dict[str, Forecast]],
    Dict[str, Dict[str, int]],
    List[str],
]:
    forecasts: Dict[str, Forecast] = {}
    opco_forecasts: Dict[str, Dict[str, Forecast]] = {}
    weather_shifts: Dict[str, Dict[str, int]] = {}
    build_notes: List[str] = []

    for label, (scenario, _) in SCENARIOS.items():
        weather_shift = build_weather_shift(projects, scenario)
        weather_shifts[label] = weather_shift
        try:
            by_opco = build_all_opcos(
                transactions,
                projects,
                scenario=scenario,
                cfg=cfg,
                weather_shift=weather_shift,
            )
            portfolio = by_opco.get("PORTFOLIO")
            if portfolio is None:
                raise KeyError("build_all_opcos did not return PORTFOLIO")
            opco_forecasts[label] = by_opco
            forecasts[label] = portfolio
        except Exception as exc:
            forecast = build_forecast(
                transactions,
                projects,
                scenario=scenario,
                cfg=cfg,
                weather_shift=weather_shift,
            )
            forecasts[label] = forecast
            opco_forecasts[label] = {"PORTFOLIO": forecast}
            build_notes.append(
                f"{label}: build_all_opcos failed; used build_forecast fallback ({exc})"
            )

    return forecasts, opco_forecasts, weather_shifts, build_notes


def load_stub_state(note: str = "") -> DashboardState:
    cfg = ForecastConfig()
    transactions, projects = make_stub(cfg)
    forecasts, opco_forecasts, weather_shifts, build_notes = build_forecast_bundle(
        transactions, projects, cfg
    )
    return DashboardState(
        cfg=cfg,
        transactions=transactions,
        projects=projects,
        forecasts=forecasts,
        opco_forecasts=opco_forecasts,
        weather_shifts=weather_shifts,
        data_label="Demo stub data",
        data_note=note or "Using synthetic Lane B/Lane C demo data.",
        build_notes=build_notes,
        using_stub=True,
    )


DEFAULT_TXN_PATH = "data/transactions.csv"
DEFAULT_PL_PATH = "data/Altis Groep — Portfolio P&L Data (Aggregated).json"


def load_real_state(transactions_path: str, projects_path: str) -> DashboardState:
    # Use the engine's one-call real-data loader: real reconciled transactions +
    # a revenue-calibrated project/WIP pipeline + covenant inputs + opco mapping +
    # a documented opening-cash assumption. The "Projects" path picker is reused
    # here as the P&L JSON path; leave it blank to use the default.
    from engine.load import load_full_state

    cfg = ForecastConfig()
    resolved_transactions = resolve_data_path(transactions_path or DEFAULT_TXN_PATH, "Transactions")
    pl_path = resolve_data_path(projects_path, "P&L") if projects_path.strip() else DEFAULT_PL_PATH
    transactions, projects, cfg, summary = load_full_state(resolved_transactions, pl_path, cfg)
    if not any(t.status in ("open_ar", "open_ap", "wip") for t in transactions):
        raise ValueError(
            "Selected transactions file has no forecastable rows — did you pick the "
            "right file? Use data/transactions.csv (the reconciled table).")
    forecasts, opco_forecasts, weather_shifts, build_notes = build_forecast_bundle(
        transactions, projects, cfg
    )
    return DashboardState(
        cfg=cfg,
        transactions=transactions,
        projects=projects,
        forecasts=forecasts,
        opco_forecasts=opco_forecasts,
        weather_shifts=weather_shifts,
        data_label="Real data",
        data_note=(
            f"Loaded {len(transactions):,} transactions + "
            f"{summary.get('pipeline_projects', 0)} pipeline projects; "
            f"opening cash EUR {cfg.opening_balance:,.0f}."
        ),
        transaction_summary=summary,
        build_notes=build_notes,
        using_stub=False,
    )


def load_dashboard_state(
    data_mode: str,
    transactions_path: str = "",
    projects_path: str = "",
) -> DashboardState:
    if data_mode == "Demo stub data":
        return load_stub_state()

    try:
        return load_real_state(transactions_path, projects_path)
    except Exception as exc:
        return load_stub_state(
            f"Real data could not be loaded, so the dashboard fell back to demo stub data. "
            f"Reason: {exc}"
        )


def cash_totals(forecast: Forecast) -> Tuple[float, float, float]:
    cash_in = sum(c.value for c in forecast.contributions if c.value > 0)
    cash_out = sum(c.value for c in forecast.contributions if c.value < 0)
    return cash_in, cash_out, cash_in + cash_out


def cash_totals_for_week(forecast: Forecast, week: int) -> Tuple[float, float]:
    values = [c.value for c in forecast.contributions if c.week == week]
    cash_in = sum(v for v in values if v > 0)
    cash_out = sum(v for v in values if v < 0)
    return cash_in, cash_out


def worst_light(lights: Iterable[str]) -> str:
    lights = list(lights)
    if "red" in lights:
        return "red"
    if "amber" in lights:
        return "amber"
    return "green"


def render_light(light: str, label: str = "Covenant status") -> None:
    text, background, border = LIGHT_COLORS.get(light, LIGHT_COLORS["amber"])
    st.markdown(
        f"""
        <div style="
            border: 1px solid {border};
            background: {background};
            color: {text};
            border-radius: 8px;
            padding: 0.85rem 1rem;
            margin: 0.5rem 0 1rem 0;
        ">
            <div style="font-size: 0.82rem; font-weight: 600;">{label}</div>
            <div style="font-size: 1.35rem; font-weight: 800; letter-spacing: 0;">
                {light.upper()}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def build_week_rows(forecast: Forecast) -> List[Dict[str, object]]:
    drivers = forecast.drivers()
    net_cash = forecast.net_cash()
    running_balance = forecast.running_balance()
    headroom = forecast.covenant_headroom()
    lights = forecast.covenant_lights()

    rows: List[Dict[str, object]] = []
    for week_index, week_start in enumerate(forecast.weeks):
        cash_in, cash_out = cash_totals_for_week(forecast, week_index)
        row: Dict[str, object] = {
            "week": f"W{week_index}",
            "week_start": week_start.isoformat(),
            "cash_in": round(cash_in, 2),
            "cash_out": round(abs(cash_out), 2),
            "net_cash": round(net_cash[week_index], 2),
            "ending_cash": round(running_balance[week_index], 2),
            "covenant_headroom": round(headroom[week_index], 2),
            "light": lights[week_index],
        }
        for driver, label in DRIVER_LABELS.items():
            row[label] = round(drivers.get(driver, [0.0] * len(forecast.weeks))[week_index], 2)
        rows.append(row)
    return rows


def warning_week_label(forecast: Forecast) -> str:
    warning_week = covenant.first_breach_week(forecast.covenant_lights())
    if warning_week is None:
        return "None"
    return f"W{warning_week} - {forecast.weeks[warning_week].isoformat()}"


def covenant_week_rows(forecast: Forecast) -> List[Dict[str, object]]:
    headroom = forecast.covenant_headroom()
    lights = forecast.covenant_lights()
    running_balance = forecast.running_balance()
    return [
        {
            "week": f"W{index}",
            "week_start": week.isoformat(),
            "ending_cash": round(running_balance[index], 2),
            "covenant_headroom": round(headroom[index], 2),
            "traffic_light": lights[index],
        }
        for index, week in enumerate(forecast.weeks)
    ]


def render_covenant_panel(forecast: Forecast, title: str = "Covenant") -> None:
    headroom = forecast.covenant_headroom()
    lights = forecast.covenant_lights()
    current_headroom = headroom[0] if headroom else 0.0
    minimum_headroom = min(headroom) if headroom else 0.0

    st.markdown(f"**{title}**")
    cols = st.columns(3)
    cols[0].metric("Current headroom (W0)", format_eur(current_headroom))
    cols[1].metric("Minimum headroom", format_eur(minimum_headroom))
    cols[2].metric("First amber/red", warning_week_label(forecast))

    render_light(worst_light(lights), "Covenant traffic light")

    st.markdown("**Covenant by week**")
    st.dataframe(covenant_week_rows(forecast), use_container_width=True, hide_index=True)


def source_label(record_id: str, transactions_by_id: Dict[str, Transaction]) -> str:
    txn = transactions_by_id.get(record_id)
    if not txn:
        return record_id
    return f"{record_id} ({txn.source_system}, {txn.source_file}:{txn.source_row})"


def trace_rows(
    forecast: Forecast,
    week: int,
    transactions_by_id: Dict[str, Transaction],
    driver: Optional[str] = None,
) -> List[Dict[str, object]]:
    rows = []
    for item in forecast.trace(week, driver):
        rows.append(
            {
                "driver": DRIVER_LABELS.get(item.driver, item.driver),
                "value": round(item.value, 2),
                "source_records": ", ".join(
                    source_label(record_id, transactions_by_id)
                    for record_id in item.contributing_records
                ),
                "assumptions": ", ".join(item.assumptions_applied) or "none",
                "scenario": item.scenario,
                "weather_shift": format_shift(item.toggle_values.get("weather_shift", {})),
                "computation": item.computation,
            }
        )
    return rows


def risk_level(project: Project, weather_shift: Dict[str, int]) -> Tuple[str, str]:
    delay = weather_shift.get(project.project_id, 0)
    score = 0
    reasons = []
    if project.weather_exposure >= 0.75:
        score += 1
        reasons.append("high weather exposure")
    if delay > 0:
        score += 1
        reasons.append("scenario delay")
    if project.wip_to_date >= 75_000:
        score += 1
        reasons.append("large WIP balance")

    if score >= 2:
        return "High", ", ".join(reasons)
    if score == 1:
        return "Watch", ", ".join(reasons)
    return "Stable", "no material scenario pressure"


def shifted_milestone_rows(projects: List[Project], weather_shift: Dict[str, int]) -> List[Dict[str, object]]:
    rows = []
    for project in projects:
        project_shift = weather_shift.get(project.project_id, 0)
        for milestone in project.milestones:
            if not milestone.weather_dependent or project_shift == 0:
                continue
            shifted_date = milestone.planned_date + timedelta(days=project_shift)
            rows.append(
                {
                    "project": project.project_id,
                    "opco": project.opco,
                    "milestone": milestone.description,
                    "planned_date": milestone.planned_date.isoformat(),
                    "scenario_date": shifted_date.isoformat(),
                    "shift": format_days(project_shift),
                    "amount": round(milestone.amount, 2),
                }
            )
    return rows


def project_contribution_rows(
    forecast: Forecast,
    transactions: List[Transaction],
    project_id: str,
) -> List[Dict[str, object]]:
    record_ids = {txn.record_id for txn in transactions if txn.project_id == project_id}
    rows = []
    for item in forecast.contributions:
        if not (record_ids & set(item.contributing_records)):
            continue
        rows.append(
            {
                "week": f"W{item.week}",
                "driver": DRIVER_LABELS.get(item.driver, item.driver),
                "value": round(item.value, 2),
                "records": ", ".join(item.contributing_records),
                "assumptions": ", ".join(item.assumptions_applied) or "none",
                "computation": item.computation,
            }
        )
    return rows


def render_cfo_tab(
    forecast: Forecast,
    transactions_by_id: Dict[str, Transaction],
) -> None:
    st.subheader("CFO")
    st.caption("13-week cash forecast by driver, generated from one forecast object.")

    cash_in, cash_out, net_cash = cash_totals(forecast)
    ending_cash = forecast.running_balance()[-1]

    metric_cols = st.columns(4)
    metric_cols[0].metric("Cash in", format_eur(cash_in))
    metric_cols[1].metric("Cash out", format_eur(abs(cash_out)))
    metric_cols[2].metric("Net cash", format_eur(net_cash))
    metric_cols[3].metric("Ending cash", format_eur(ending_cash))

    render_covenant_panel(forecast, "Covenant")

    week_rows = build_week_rows(forecast)
    st.markdown("**13-week forecast**")
    st.dataframe(week_rows, use_container_width=True, hide_index=True)

    st.markdown("**Ending cash**")
    st.line_chart({"Ending cash": [row["ending_cash"] for row in week_rows]})

    st.markdown("**Trace drill-down**")
    week_options = {
        f"W{index} - {week.isoformat()}": index
        for index, week in enumerate(forecast.weeks)
    }
    selected_week_label = st.selectbox("Week", list(week_options), key="cfo_trace_week")
    selected_week = week_options[selected_week_label]

    active_drivers = [
        driver for driver, values in forecast.drivers().items()
        if any(abs(value) > 0.5 for value in values)
    ]
    driver_labels = ["All drivers"] + [DRIVER_LABELS.get(driver, driver) for driver in active_drivers]
    selected_driver_label = st.selectbox("Driver", driver_labels, key="cfo_trace_driver")
    selected_driver = None
    if selected_driver_label != "All drivers":
        selected_driver = next(
            driver for driver in active_drivers
            if DRIVER_LABELS.get(driver, driver) == selected_driver_label
        )

    rows = trace_rows(forecast, selected_week, transactions_by_id, selected_driver)
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No forecast contributions in this week for the selected driver.")


def render_opco_tab(projects: List[Project], weather_shift: Dict[str, int]) -> None:
    st.subheader("Opco MD")
    st.caption("Project risk, WIP exposure, and scenario-shifted milestones.")

    if not projects:
        st.info("No project records are loaded. Add a projects JSON file to populate this view.")
        return

    opco_rows = []
    for opco in sorted({project.opco for project in projects}):
        opco_projects = [project for project in projects if project.opco == opco]
        opco_rows.append(
            {
                "opco": opco,
                "projects": len(opco_projects),
                "wip_exposure": round(sum(project.wip_to_date for project in opco_projects), 2),
                "contract_value": round(sum(project.contract_value for project in opco_projects), 2),
                "projects_at_risk": sum(
                    1 for project in opco_projects
                    if risk_level(project, weather_shift)[0] == "High"
                ),
            }
        )

    st.markdown("**WIP exposure by opco**")
    st.dataframe(opco_rows, use_container_width=True, hide_index=True)

    st.markdown("**Project risk cards**")
    for project in projects:
        level, reason = risk_level(project, weather_shift)
        delay = weather_shift.get(project.project_id, 0)
        with st.container(border=True):
            top = st.columns([2, 1, 1, 1])
            top[0].markdown(f"**{project.project_id} - {project.customer}**")
            top[0].caption(project.opco)
            top[1].metric("Risk", level)
            top[2].metric("WIP", format_eur(project.wip_to_date))
            top[3].metric("Shift", format_days(delay))
            st.progress(int(max(0, min(project.weather_exposure, 1)) * 100))
            st.caption(
                f"Weather exposure {project.weather_exposure:.0%}; "
                f"completion {project.percent_complete:.0%}; {reason}."
            )

    st.markdown("**Scenario-shifted milestones**")
    rows = shifted_milestone_rows(projects, weather_shift)
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No explicit weather-dependent milestones are shifted in this scenario.")


def render_project_lead_tab(
    projects: List[Project],
    transactions: List[Transaction],
    forecast: Forecast,
    weather_shift: Dict[str, int],
) -> None:
    st.subheader("Project Lead")
    st.caption("Next invoiceable milestone, weather timing, and project-level cash events.")

    if not projects:
        st.info("No project records are loaded. Add a projects JSON file to populate this view.")
        return

    project_lookup = {project.project_id: project for project in projects}
    selected_project_id = st.selectbox(
        "Project",
        list(project_lookup),
        format_func=lambda project_id: f"{project_id} - {project_lookup[project_id].customer}",
        key="project_lead_project",
    )
    project = project_lookup[selected_project_id]
    project_shift = weather_shift.get(project.project_id, 0)
    milestones = sorted(project.milestones, key=lambda milestone: milestone.planned_date)
    next_milestone = next(
        (milestone for milestone in milestones if milestone.status != "paid"),
        None,
    )

    if next_milestone:
        applies = next_milestone.weather_dependent
        effective_shift = project_shift if applies else 0
        scenario_date = next_milestone.planned_date + timedelta(days=effective_shift)

        metric_cols = st.columns(4)
        metric_cols[0].metric("Milestone", next_milestone.description)
        metric_cols[1].metric("Amount", format_eur(next_milestone.amount))
        metric_cols[2].metric("Planned", next_milestone.planned_date.isoformat())
        metric_cols[3].metric("Scenario date", scenario_date.isoformat())

        if effective_shift > 0:
            st.warning(
                f"Weather delays this invoiceable milestone by {effective_shift} days. "
                "Collections move later through the payment-lag driver."
            )
        elif effective_shift < 0:
            st.success(
                f"Dry weather pulls this milestone {abs(effective_shift)} days earlier. "
                "Collections may land earlier in the 13-week forecast."
            )
        else:
            st.info("No weather delay is applied to this milestone in the selected scenario.")
    else:
        st.info("No explicit invoiceable milestone is available for this project in the stub data.")

    st.markdown("**Weather explanation**")
    st.write(
        "Lane C passes project-level working-day shifts into the engine. "
        "The engine shifts weather-exposed revenue and milestone-tied subcontractor timing, "
        "while committed materials stay put. That creates the cash squeeze shown in the demo."
    )

    st.markdown("**Forecast events for this project**")
    rows = project_contribution_rows(forecast, transactions, project.project_id)
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No forecast cash events for this project land inside the 13-week horizon.")


def render_board_tab(
    forecast: Forecast,
    base_forecast: Forecast,
    projects: List[Project],
    weather_shift: Dict[str, int],
) -> None:
    st.subheader("PE Board")
    st.caption("Consolidated covenant status and portfolio-level summary.")

    render_covenant_panel(forecast, "Consolidated covenant")

    cash_in, cash_out, net_cash = cash_totals(forecast)
    ending_cash = forecast.running_balance()[-1]
    at_risk = sum(1 for project in projects if risk_level(project, weather_shift)[0] == "High")

    metric_cols = st.columns(4)
    metric_cols[0].metric("Ending cash", format_eur(ending_cash))
    metric_cols[1].metric("Portfolio cash in", format_eur(cash_in))
    metric_cols[2].metric("Portfolio cash out", format_eur(abs(cash_out)))
    metric_cols[3].metric("Portfolio net cash", format_eur(net_cash))

    summary_cols = st.columns(2)
    summary_cols[0].metric("High-risk projects", str(at_risk))
    summary_cols[1].metric("Projects", str(len(projects)))

    st.markdown("**Scenario movement vs base**")
    ending_delta = forecast.running_balance()[-1] - base_forecast.running_balance()[-1]
    st.write(f"Ending cash movement vs base: **{format_eur(ending_delta)}**")

    movers = biggest_movers(base_forecast, forecast, top=5)
    if movers:
        st.dataframe(
            [
                {
                    "week": f"W{mover.week}",
                    "driver": DRIVER_LABELS.get(mover.driver, mover.driver),
                    "base": round(mover.base_value, 2),
                    "scenario": round(mover.scenario_value, 2),
                    "delta": round(mover.delta, 2),
                }
                for mover in movers
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No scenario movement versus base.")


def main() -> None:
    st.set_page_config(
        page_title="Altis Lane C Dashboard",
        page_icon=None,
        layout="wide",
    )

    st.title("Altis Weather-Aware Cash Forecast")
    st.caption("Lane C dashboard over the existing forecast engine.")

    data_mode = st.sidebar.selectbox(
        "Data mode",
        ["Demo stub data", "Real data"],
        key="data_mode",
    )

    transactions_path = ""
    projects_path = ""
    if data_mode == "Real data":
        st.sidebar.markdown("**Real data files**")
        transactions_path = sidebar_path_picker(
            "transactions",
            TRANSACTION_SUFFIXES,
            "transactions",
            prefer="transactions.csv",
        )
        projects_path = sidebar_path_picker(
            "P&L (or leave blank)",
            PROJECT_SUFFIXES,
            "projects",
            prefer="P&L",
        )

    state = load_dashboard_state(data_mode, transactions_path, projects_path)
    transactions = state.transactions
    projects = state.projects
    forecasts = state.forecasts
    transactions_by_id = {txn.record_id: txn for txn in transactions}

    st.sidebar.markdown("**Data status**")
    if state.using_stub and data_mode == "Real data":
        st.sidebar.warning(state.data_note)
    elif state.using_stub:
        st.sidebar.info(state.data_note)
    else:
        st.sidebar.success(state.data_note)

    if state.transaction_summary:
        with st.sidebar.expander("Transaction load summary"):
            st.write(state.transaction_summary)

    if state.build_notes:
        with st.sidebar.expander("Forecast build notes"):
            for note in state.build_notes:
                st.write(note)

    selected_label = st.sidebar.selectbox("Scenario", list(SCENARIOS), key="scenario")
    scenario_name, scenario_note = SCENARIOS[selected_label]
    weather_shift = state.weather_shifts.get(selected_label, {})
    forecast = forecasts[selected_label]
    base_forecast = forecasts["Base"]

    st.sidebar.markdown("**Scenario input**")
    st.sidebar.write(scenario_note)
    st.sidebar.caption(f"Engine scenario: `{scenario_name}`")
    exposed_project_ids = [
        project.project_id for project in weather_exposed_projects(projects)
    ]
    if not exposed_project_ids:
        st.sidebar.warning(
            "No weather-exposed projects are loaded. Wet/dry scenarios will not move forecast timing."
        )
    elif weather_shift:
        st.sidebar.caption(f"Shifted project IDs: {', '.join(sorted(weather_shift))}")
        st.sidebar.caption(f"Weather shift: {format_shift(weather_shift)}")
    else:
        st.sidebar.caption(
            f"Weather-exposed project IDs: {', '.join(sorted(exposed_project_ids))}"
        )
        st.sidebar.caption("Weather shift: none for the base scenario")
    st.sidebar.caption(
        f"Forecast scope: {', '.join(state.opco_forecasts.get(selected_label, {}).keys())}"
    )

    cfo_tab, opco_tab, project_tab, board_tab = st.tabs(
        ["CFO", "Opco MD", "Project Lead", "PE Board"]
    )

    with cfo_tab:
        render_cfo_tab(forecast, transactions_by_id)

    with opco_tab:
        render_opco_tab(projects, weather_shift)

    with project_tab:
        render_project_lead_tab(projects, transactions, forecast, weather_shift)

    with board_tab:
        render_board_tab(forecast, base_forecast, projects, weather_shift)


if __name__ == "__main__":
    main()
