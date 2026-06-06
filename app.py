from __future__ import annotations

import base64
import inspect
from dataclasses import dataclass, field
from datetime import timedelta
from html import escape
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import altair as alt
import pandas as pd
import pydeck as pdk
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

# Importing the panel also loads the local .env (via llm_gl_mapping), so
# OPENAI_API_KEY is picked up automatically when the app runs.
from mapping_panel import render_mapping_review


ScenarioConfig = Tuple[str, str]

SCENARIOS: Dict[str, ScenarioConfig] = {
    "Base": (
        "base",
        "Baseline forecast with no incremental weather shift.",
    ),
    "Wet Quarter": (
        "wet-quarter",
        "Weather-exposed projects lose workable days, pushing billing and cash later.",
    ),
    "Dry Quarter": (
        "dry-quarter",
        "Weather-exposed projects regain workable days, pulling some cash earlier.",
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

DRIVER_COLORS = {
    "Milestone billing": "#143B5A",
    "Customer payment": "#47A885",
    "Materials": "#F59E0B",
    "Subcontractor": "#6366F1",
    "VAT remittance": "#EF4444",
    "Other": "#94A3B8",
}

BRAND_NAVY = "#143B5A"
BRAND_GREEN = "#47A885"
BRAND_BG = "#F8FAFC"
BRAND_CARD = "#FFFFFF"
BRAND_AMBER = "#F59E0B"
BRAND_RED = "#EF4444"

LIGHT_META = {
    "green": ("SAFE", "#166534", "#ECFDF5", "#BBF7D0"),
    "amber": ("WARNING", "#78350F", "#FFFBEB", "#FDE68A"),
    "red": ("RISK", "#991B1B", "#FEF2F2", "#FECACA"),
}

THEMES = {
    "Light Mode": {
        "bg": "#F8FAFC",
        "card": "#FFFFFF",
        "card_alt": "#F1F5F9",
        "sidebar": "#FFFFFF",
        "line": "#E2E8F0",
        "text": "#0F172A",
        "muted": "#64748B",
        "navy_text": BRAND_NAVY,
        "shadow": "0 10px 28px rgba(20, 59, 90, 0.07)",
        "chart_bg": "#FFFFFF",
        "tab_selected": "#ECFDF5",
        "trace_bg": "#FFFFFF",
        "info_bg": "#EFF6FF",
        "info_text": "#1E3A8A",
        "info_border": "#BFDBFE",
        "warning_bg": "#FFFBEB",
        "warning_text": "#78350F",
        "warning_border": "#FDE68A",
        "success_bg": "#ECFDF5",
        "success_text": "#14532D",
        "success_border": "#BBF7D0",
        "danger_bg": "#FEF2F2",
        "danger_text": "#7F1D1D",
        "danger_border": "#FECACA",
    },
    "Dark Mode": {
        "bg": "#0B1220",
        "card": "#111827",
        "card_alt": "#172033",
        "sidebar": "#0F172A",
        "line": "#263246",
        "text": "#E5E7EB",
        "muted": "#A7B3C6",
        "navy_text": "#DDEBFF",
        "shadow": "0 16px 34px rgba(0, 0, 0, 0.28)",
        "chart_bg": "#111827",
        "tab_selected": "#12322E",
        "trace_bg": "#101827",
        "info_bg": "#0F2A45",
        "info_text": "#DBEAFE",
        "info_border": "#1D4ED8",
        "warning_bg": "#3A2708",
        "warning_text": "#FDE68A",
        "warning_border": "#B45309",
        "success_bg": "#0D2B25",
        "success_text": "#BBF7D0",
        "success_border": "#047857",
        "danger_bg": "#3B1115",
        "danger_text": "#FECACA",
        "danger_border": "#B91C1C",
    },
}

TRANSACTION_SUFFIXES = {".csv", ".parquet", ".duckdb", ".db", ".sqlite"}
PROJECT_SUFFIXES = {".json"}
LOGO_PATH = Path("assets/altis_logo.png")
DEFAULT_TXN_PATH = Path("data/transactions.csv")

COMPANY_LOCATIONS = {
    "andijk": (52.7442, 5.2217),
    "brunssum": (50.9460, 5.9708),
    "heeze": (51.3827, 5.5715),
    "winschoten": (53.1442, 7.0349),
    "opconoord": (52.7442, 5.2217),
    "opcozuid": (50.9460, 5.9708),
}

PREFIX_LOCATIONS = {
    "AND": COMPANY_LOCATIONS["andijk"],
    "BRU": COMPANY_LOCATIONS["brunssum"],
    "HEE": COMPANY_LOCATIONS["heeze"],
    "WIN": COMPANY_LOCATIONS["winschoten"],
}


@dataclass
class DashboardState:
    cfg: ForecastConfig
    transactions: List[Transaction]
    projects: List[Project]
    forecasts: Dict[str, Forecast]
    opco_forecasts: Dict[str, Dict[str, Forecast]] = field(default_factory=dict)
    weather_shifts: Dict[str, Dict[str, int]] = field(default_factory=dict)
    data_note: str = ""
    transaction_summary: Optional[Dict[str, object]] = None
    build_notes: List[str] = field(default_factory=list)
    using_stub: bool = True


def format_eur(value: float) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}EUR {abs(value):,.0f}"


def format_ratio(value: float) -> str:
    return f"{value:,.2f}"


def format_headroom(forecast: Forecast, value: float) -> str:
    metric = getattr(forecast.cfg, "covenant_metric", "min_liquidity")
    if metric == "min_liquidity":
        return format_eur(value)
    if metric == "leverage":
        return f"{value:,.2f} turns"
    if metric == "dscr":
        return f"{value:,.2f}x"
    return format_ratio(value)


def format_days(days: int) -> str:
    if days > 0:
        return f"+{days} days"
    if days < 0:
        return f"{days} days"
    return "0 days"


def format_shift(weather_shift: Dict[str, int]) -> str:
    if not weather_shift:
        return "none"
    return ", ".join(f"{project}: {days:+d}d" for project, days in sorted(weather_shift.items()))


def weather_exposed_projects(projects: List[Project]) -> List[Project]:
    return [project for project in projects if project.weather_exposure > 0]


def build_weather_shift(projects: List[Project], scenario: str, month: int = 1) -> Dict[str, int]:
    from engine.weather import scenario_shift

    if "month" in inspect.signature(scenario_shift).parameters:
        return scenario_shift(projects, scenario, month=month)
    return scenario_shift(projects, scenario)


def data_uri(path: Path) -> str:
    mime = {
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "image/png")
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def logo_html(size: str = "sidebar") -> str:
    if LOGO_PATH.exists():
        max_height = "54px" if size == "sidebar" else "64px"
        return (
            f'<img src="{data_uri(LOGO_PATH)}" alt="Altis Groep" class="altis-logo" '
            f'style="max-height:{max_height};max-width:210px;object-fit:contain;" />'
        )
    return '<div class="wordmark">ALTIS<br/><span>GROEP</span></div>'


def inject_styles(theme_mode: str) -> None:
    theme = THEMES[theme_mode]
    st.markdown(
        f"""
        <style>
        :root {{
            --navy: {BRAND_NAVY};
            --green: {BRAND_GREEN};
            --bg: {theme["bg"]};
            --card: {theme["card"]};
            --card-alt: {theme["card_alt"]};
            --amber: {BRAND_AMBER};
            --red: {BRAND_RED};
            --line: {theme["line"]};
            --muted: {theme["muted"]};
            --text: {theme["text"]};
            --navy-text: {theme["navy_text"]};
            --sidebar-bg: {theme["sidebar"]};
            --shadow-soft: {theme["shadow"]};
            --chart-bg: {theme["chart_bg"]};
            --tab-selected: {theme["tab_selected"]};
            --trace-bg: {theme["trace_bg"]};
            --info-bg: {theme["info_bg"]};
            --info-text: {theme["info_text"]};
            --info-border: {theme["info_border"]};
            --warning-bg: {theme["warning_bg"]};
            --warning-text: {theme["warning_text"]};
            --warning-border: {theme["warning_border"]};
            --success-bg: {theme["success_bg"]};
            --success-text: {theme["success_text"]};
            --success-border: {theme["success_border"]};
            --danger-bg: {theme["danger_bg"]};
            --danger-text: {theme["danger_text"]};
            --danger-border: {theme["danger_border"]};
        }}

        .stApp {{
            background: var(--bg);
            color: var(--text);
        }}

        .main .block-container {{
            max-width: 1400px;
            padding-top: 1.1rem;
            padding-bottom: 3rem;
        }}

        [data-testid="stSidebar"] {{
            background: var(--sidebar-bg);
            border-right: 1px solid var(--line);
            box-shadow: var(--shadow-soft);
        }}

        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stSidebar"] label {{
            color: var(--navy-text);
        }}

        [data-testid="stMarkdownContainer"] p,
        [data-testid="stCaptionContainer"],
        label,
        span {{
            color: var(--text);
        }}

        .wordmark {{
            color: var(--navy-text);
            font-weight: 900;
            font-size: 1.25rem;
            line-height: 0.95;
        }}

        .wordmark span {{
            color: var(--green);
            font-size: 0.9rem;
            letter-spacing: 0.08rem;
        }}

        input,
        textarea,
        [data-baseweb="select"] > div {{
            background: var(--card-alt);
            color: var(--text);
            border-color: var(--line);
        }}

        [data-baseweb="popover"] {{
            color: var(--text);
        }}

        h1, h2, h3 {{
            color: var(--navy-text);
            letter-spacing: 0;
        }}

        .side-logo {{
            padding: 0.7rem 0 1.0rem 0;
            border-bottom: 1px solid var(--line);
            margin-bottom: 1rem;
        }}

        .side-section {{
            font-size: 0.75rem;
            font-weight: 800;
            color: var(--muted);
            letter-spacing: 0.04rem;
            text-transform: uppercase;
            margin: 1.2rem 0 0.35rem 0;
        }}

        .hero {{
            background: var(--card);
            border: 1px solid var(--line);
            border-radius: 18px;
            box-shadow: var(--shadow-soft);
            padding: 1.15rem 1.3rem;
            margin-bottom: 1rem;
        }}

        .hero-grid {{
            display: grid;
            grid-template-columns: minmax(180px, 260px) 1fr auto;
            gap: 1rem;
            align-items: center;
        }}

        .hero-title {{
            color: var(--navy-text);
            font-size: clamp(1.6rem, 3vw, 2.45rem);
            font-weight: 850;
            line-height: 1.06;
            margin: 0;
        }}

        .hero-subtitle {{
            color: var(--muted);
            margin-top: 0.28rem;
            font-weight: 600;
        }}

        .badge {{
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            background: var(--success-bg);
            border: 1px solid var(--success-border);
            color: var(--success-text);
            font-size: 0.8rem;
            font-weight: 800;
            padding: 0.35rem 0.75rem;
            white-space: nowrap;
        }}

        .card {{
            background: var(--card);
            border: 1px solid var(--line);
            border-radius: 16px;
            box-shadow: var(--shadow-soft);
            padding: 1rem 1.05rem;
            min-height: 104px;
        }}

        .card-label {{
            color: var(--muted);
            font-size: 0.78rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.035rem;
        }}

        .card-value {{
            color: var(--navy-text);
            font-size: 1.6rem;
            line-height: 1.15;
            font-weight: 850;
            margin-top: 0.35rem;
        }}

        .card-note {{
            color: var(--muted);
            font-size: 0.86rem;
            margin-top: 0.3rem;
        }}

        .panel-title {{
            color: var(--navy-text);
            font-size: 1.08rem;
            font-weight: 850;
            margin: 1.05rem 0 0.5rem 0;
        }}

        .status-card {{
            border-radius: 16px;
            border: 1px solid;
            padding: 0.95rem 1rem;
            box-shadow: var(--shadow-soft);
        }}

        .status-label {{
            color: var(--muted);
            font-size: 0.78rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.035rem;
        }}

        .status-value {{
            font-size: 1.45rem;
            font-weight: 900;
            margin-top: 0.15rem;
        }}

        .trace-card {{
            background: var(--trace-bg);
            border: 1px solid var(--success-border);
            border-left: 5px solid var(--green);
            border-radius: 14px;
            box-shadow: var(--shadow-soft);
            padding: 0.9rem 1rem;
            margin: 0.75rem 0;
        }}

        .trace-flow {{
            color: var(--navy-text);
            font-weight: 850;
            font-size: 0.95rem;
            margin-bottom: 0.45rem;
        }}

        .trace-meta {{
            color: var(--muted);
            font-size: 0.88rem;
            line-height: 1.45;
        }}

        div[data-testid="stVerticalBlockBorderWrapper"] {{
            border-color: var(--line);
            border-radius: 16px;
            background: var(--card);
            box-shadow: var(--shadow-soft);
        }}

        [data-testid="stMetric"] {{
            background: var(--card);
            border: 1px solid var(--line);
            border-radius: 14px;
            padding: 0.8rem 0.9rem;
            box-shadow: var(--shadow-soft);
        }}

        [data-testid="stMetricLabel"] {{
            color: var(--muted);
            font-weight: 800;
        }}

        [data-testid="stMetricValue"] {{
            color: var(--navy-text);
            font-weight: 850;
        }}

        .stTabs [data-baseweb="tab-list"] {{
            gap: 0.45rem;
            border-bottom: 1px solid var(--line);
            margin-bottom: 0.8rem;
        }}

        .stTabs [data-baseweb="tab"] {{
            color: var(--muted);
            font-weight: 800;
            border-radius: 12px 12px 0 0;
            padding-left: 1rem;
            padding-right: 1rem;
        }}

        .stTabs [aria-selected="true"] {{
            background: var(--tab-selected);
            color: var(--navy-text);
            border-bottom: 3px solid var(--green);
        }}

        .stDataFrame {{
            border: 1px solid var(--line);
            border-radius: 14px;
            overflow: hidden;
            box-shadow: var(--shadow-soft);
        }}

        div[data-testid="stAlert"] {{
            background: var(--info-bg);
            color: var(--info-text);
            border: 1px solid var(--info-border);
            border-radius: 12px;
        }}

        div[data-testid="stAlert"] * {{
            color: inherit;
        }}

        .alert-box {{
            border-radius: 12px;
            border: 1px solid;
            padding: 0.8rem 0.95rem;
            margin: 0.65rem 0;
            font-weight: 650;
            line-height: 1.45;
        }}

        .alert-info {{
            background: var(--info-bg);
            border-color: var(--info-border);
            color: var(--info-text);
        }}

        .alert-warning {{
            background: var(--warning-bg);
            border-color: var(--warning-border);
            color: var(--warning-text);
        }}

        .alert-success {{
            background: var(--success-bg);
            border-color: var(--success-border);
            color: var(--success-text);
        }}

        .alert-danger {{
            background: var(--danger-bg);
            border-color: var(--danger-border);
            color: var(--danger-text);
        }}

        @media (max-width: 900px) {{
            .hero-grid {{
                grid-template-columns: 1fr;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    # The logo is navy-on-transparent. On a dark background that's low-contrast,
    # so in dark mode we sit it on a soft white rounded chip (brand colours stay
    # intact). Light mode needs nothing — transparent on white already looks clean.
    if theme_mode == "Dark Mode":
        st.markdown(
            "<style>.altis-logo{background:#FFFFFF;border-radius:12px;"
            "padding:8px 14px;box-shadow:0 2px 10px rgba(0,0,0,0.35);}</style>",
            unsafe_allow_html=True,
        )


def html_card(label: str, value: str, note: str = "") -> None:
    st.markdown(
        f"""
        <div class="card">
            <div class="card-label">{escape(label)}</div>
            <div class="card-value">{escape(value)}</div>
            <div class="card-note">{escape(note)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def panel_title(title: str) -> None:
    st.markdown(f'<div class="panel-title">{escape(title)}</div>', unsafe_allow_html=True)


def current_theme() -> Dict[str, str]:
    mode = st.session_state.get("theme_mode", "Light Mode")
    return THEMES.get(mode, THEMES["Light Mode"])


def themed_chart(chart: alt.Chart) -> alt.Chart:
    theme = current_theme()
    return (
        chart
        .configure(background=theme["chart_bg"])
        .configure_view(stroke=theme["line"])
        .configure_axis(
            labelColor=theme["text"],
            titleColor=theme["muted"],
            gridColor=theme["line"],
            domainColor=theme["line"],
            tickColor=theme["line"],
        )
        .configure_legend(labelColor=theme["text"], titleColor=theme["muted"])
        .configure_title(color=theme["navy_text"])
    )


def alert_box(message: str, tone: str = "info", container=st) -> None:
    safe_tone = tone if tone in {"info", "warning", "success", "danger"} else "info"
    container.markdown(
        f'<div class="alert-box alert-{safe_tone}">{escape(message)}</div>',
        unsafe_allow_html=True,
    )


def render_sidebar_logo() -> None:
    st.sidebar.markdown(
        f'<div class="side-logo">{logo_html("sidebar")}</div>',
        unsafe_allow_html=True,
    )


def render_hero(data_mode: str, scenario_label: str, state: DashboardState) -> None:
    mode = "Demo" if state.using_stub else "Real data"
    st.markdown(
        f"""
        <div class="hero">
            <div class="hero-grid">
                <div>{logo_html("hero")}</div>
                <div>
                    <div class="hero-title">Weather-Aware Cash Forecast</div>
                    <div class="hero-subtitle">Hackathon Prototype - one traceable engine for CFO, Opco, Project Lead, and Board views.</div>
                </div>
                <div class="badge">{escape(mode)} / {escape(scenario_label)}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def discover_files(suffixes: set[str]) -> List[str]:
    base = Path.cwd()
    out: List[str] = []
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {".git", "__pycache__", "assets", ".venv", "venv"} for part in path.parts):
            continue
        if path.suffix.lower() in suffixes:
            out.append(path.relative_to(base).as_posix())
    return sorted(out)


def default_pl_path() -> str:
    matches = sorted(Path("data").glob("Altis Groep*.json"))
    return str(matches[0]) if matches else ""


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
        f"Select {label}",
        options,
        index=default_index,
        key=f"{key}_select",
    )
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
) -> Tuple[Dict[str, Forecast], Dict[str, Dict[str, Forecast]], Dict[str, Dict[str, int]], List[str]]:
    forecasts: Dict[str, Forecast] = {}
    opco_forecasts: Dict[str, Dict[str, Forecast]] = {}
    weather_shifts: Dict[str, Dict[str, int]] = {}
    build_notes: List[str] = []

    for label, (scenario, _) in SCENARIOS.items():
        weather_shift = build_weather_shift(projects, scenario, month=cfg.anchor_monday.month)
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
            build_notes.append(f"{label}: build_all_opcos failed; used build_forecast fallback ({exc})")

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
        data_note=note or "Using synthetic Lane B/Lane C demo data.",
        build_notes=build_notes,
        using_stub=True,
    )


def load_real_state(transactions_path: str, projects_path: str) -> DashboardState:
    from engine.load import load_full_state

    txn_path = transactions_path.strip() or str(DEFAULT_TXN_PATH)
    pl_path = projects_path.strip() or default_pl_path()

    def _load(candidate_txn: str) -> Tuple[List[Transaction], List[Project], ForecastConfig, Dict[str, object]]:
        resolved_txn = resolve_data_path(candidate_txn, "Transactions")
        resolved_pl = resolve_data_path(pl_path, "P&L")
        txns, projects, cfg, summary = load_full_state(resolved_txn, resolved_pl, ForecastConfig())
        if not any(t.status in ("open_ar", "open_ap", "wip") for t in txns):
            raise ValueError("no forecastable rows")
        return txns, projects, cfg, summary

    try:
        transactions, projects, cfg, summary = _load(txn_path)
    except Exception:
        transactions, projects, cfg, summary = _load(str(DEFAULT_TXN_PATH))

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
        data_note=(
            f"Loaded {len(transactions):,} rows and {len(projects):,} projects; "
            f"opening cash {format_eur(cfg.opening_balance)}."
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
            f"Real data could not be loaded, so the dashboard fell back to demo data. Reason: {exc}"
        )


def cash_totals(forecast: Forecast) -> Tuple[float, float, float]:
    cash_in = sum(c.value for c in forecast.contributions if c.value > 0)
    cash_out = sum(c.value for c in forecast.contributions if c.value < 0)
    return cash_in, cash_out, cash_in + cash_out


def cash_totals_for_week(forecast: Forecast, week: int) -> Tuple[float, float]:
    values = [c.value for c in forecast.contributions if c.week == week]
    return sum(v for v in values if v > 0), sum(v for v in values if v < 0)


def worst_light(lights: Iterable[str]) -> str:
    light_list = list(lights)
    if "red" in light_list:
        return "red"
    if "amber" in light_list:
        return "amber"
    return "green"


def warning_week_label(forecast: Forecast) -> str:
    warning_week = covenant.first_breach_week(forecast.covenant_lights())
    if warning_week is None:
        return "None"
    return f"W{warning_week} - {forecast.weeks[warning_week].isoformat()}"


def build_week_rows(forecast: Forecast) -> List[Dict[str, object]]:
    drivers = forecast.drivers()
    net_cash = forecast.net_cash()
    running = forecast.running_balance()
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
            "ending_cash": round(running[week_index], 2),
            "covenant_headroom": round(headroom[week_index], 2),
            "traffic_light": lights[week_index],
        }
        for driver, label in DRIVER_LABELS.items():
            row[label] = round(drivers.get(driver, [0.0] * len(forecast.weeks))[week_index], 2)
        rows.append(row)
    return rows


def covenant_week_rows(forecast: Forecast) -> List[Dict[str, object]]:
    running = forecast.running_balance()
    headroom = forecast.covenant_headroom()
    lights = forecast.covenant_lights()
    return [
        {
            "week": f"W{index}",
            "week_start": week.isoformat(),
            "ending_cash": round(running[index], 2),
            "covenant_headroom": round(headroom[index], 2),
            "traffic_light": lights[index],
        }
        for index, week in enumerate(forecast.weeks)
    ]


def driver_totals(forecast: Forecast) -> pd.DataFrame:
    rows = []
    for driver, values in forecast.drivers().items():
        amount = sum(values)
        if abs(amount) > 0.5:
            rows.append(
                {
                    "driver": DRIVER_LABELS.get(driver, driver),
                    "amount": amount,
                    "absolute_amount": abs(amount),
                    "direction": "Inflow" if amount >= 0 else "Outflow",
                }
            )
    return pd.DataFrame(rows)


def weekly_driver_frame(forecast: Forecast) -> pd.DataFrame:
    rows = []
    for driver, values in forecast.drivers().items():
        label = DRIVER_LABELS.get(driver, driver)
        for index, value in enumerate(values):
            if abs(value) > 0.5:
                rows.append(
                    {
                        "week": f"W{index}",
                        "week_start": forecast.weeks[index].isoformat(),
                        "driver": label,
                        "value": value,
                    }
                )
    return pd.DataFrame(rows)


def source_label(record_id: str, transactions_by_id: Dict[str, Transaction]) -> str:
    txn = transactions_by_id.get(record_id)
    if not txn:
        if record_id.startswith("sched:"):
            return record_id.replace("sched:", "project schedule: ")
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
                "assumptions": ", ".join(item.assumptions_applied) or "none",
                "scenario": item.scenario,
                "source_records": ", ".join(
                    source_label(record_id, transactions_by_id)
                    for record_id in item.contributing_records
                ),
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


def risk_color(level: str) -> List[int]:
    return {
        "High": [239, 68, 68, 215],
        "Watch": [245, 158, 11, 215],
        "Stable": [71, 168, 133, 215],
    }.get(level, [20, 59, 90, 215])


def project_base_location(project: Project) -> Tuple[float, float]:
    opco_key = project.opco.lower().replace(" ", "")
    if opco_key in COMPANY_LOCATIONS:
        return COMPANY_LOCATIONS[opco_key]
    prefix = project.project_id.split("-")[0].upper()
    if prefix in PREFIX_LOCATIONS:
        return PREFIX_LOCATIONS[prefix]
    return 52.1326, 5.2913


def project_map_rows(projects: List[Project], weather_shift: Dict[str, int]) -> List[Dict[str, object]]:
    rows = []
    opco_counts: Dict[str, int] = {}
    for project in projects:
        index = opco_counts.get(project.opco, 0)
        opco_counts[project.opco] = index + 1
        lat, lon = project_base_location(project)
        lat += ((index % 3) - 1) * 0.018
        lon += ((index // 3) - 1) * 0.028
        risk, reason = risk_level(project, weather_shift)
        rows.append(
            {
                "project_id": project.project_id,
                "opco": project.opco,
                "customer": project.customer,
                "lat": lat,
                "lon": lon,
                "risk": risk,
                "risk_reason": reason,
                "contract_value": project.contract_value,
                "wip": project.wip_to_date,
                "weather_exposure": project.weather_exposure,
                "shift": weather_shift.get(project.project_id, 0),
                "color": risk_color(risk),
                "radius": max(5500, min(21000, project.contract_value / 24)),
            }
        )
    return rows


def shifted_milestone_rows(projects: List[Project], weather_shift: Dict[str, int]) -> List[Dict[str, object]]:
    rows = []
    for project in projects:
        project_shift = weather_shift.get(project.project_id, 0)
        for milestone in project.milestones:
            if not milestone.weather_dependent or project_shift == 0:
                continue
            rows.append(
                {
                    "project": project.project_id,
                    "opco": project.opco,
                    "milestone": milestone.description,
                    "planned_date": milestone.planned_date.isoformat(),
                    "scenario_date": (milestone.planned_date + timedelta(days=project_shift)).isoformat(),
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


def render_status_card(light: str, label: str = "Covenant traffic light") -> None:
    status, text, bg, border = LIGHT_META.get(light, LIGHT_META["amber"])
    st.markdown(
        f"""
        <div class="status-card" style="background:{bg};border-color:{border};">
            <div class="status-label">{escape(label)}</div>
            <div class="status-value" style="color:{text};">{escape(status)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_covenant_panel(forecast: Forecast, title: str) -> None:
    headroom = forecast.covenant_headroom()
    lights = forecast.covenant_lights()
    panel_title(title)
    cols = st.columns([1, 1, 1, 1])
    with cols[0]:
        html_card("Current headroom", format_headroom(forecast, headroom[0] if headroom else 0), "Week 0")
    with cols[1]:
        html_card("Minimum headroom", format_headroom(forecast, min(headroom) if headroom else 0), "Worst week")
    with cols[2]:
        html_card("First warning", warning_week_label(forecast), "Amber or red")
    with cols[3]:
        render_status_card(worst_light(lights))

    with st.expander("Covenant by week", expanded=False):
        st.dataframe(covenant_week_rows(forecast), width="stretch", hide_index=True)


def render_cash_chart(forecast: Forecast) -> None:
    df = pd.DataFrame(build_week_rows(forecast))
    df["week_start"] = pd.to_datetime(df["week_start"])
    line = (
        alt.Chart(df)
        .mark_line(color=BRAND_NAVY, strokeWidth=3, point={"filled": True, "fill": BRAND_GREEN})
        .encode(
            x=alt.X("week_start:T", title="Week"),
            y=alt.Y("ending_cash:Q", title="Ending cash"),
            tooltip=["week", "week_start:T", "ending_cash:Q", "net_cash:Q", "traffic_light"],
        )
    )
    area = (
        alt.Chart(df)
        .mark_area(color=BRAND_GREEN, opacity=0.12)
        .encode(x="week_start:T", y="ending_cash:Q")
    )
    st.altair_chart(themed_chart(area + line), use_container_width=True)


def render_driver_donut(forecast: Forecast) -> None:
    df = driver_totals(forecast)
    if df.empty:
        alert_box("No driver values in this forecast.")
        return
    chart = (
        alt.Chart(df)
        .mark_arc(innerRadius=72, outerRadius=118, cornerRadius=6)
        .encode(
            theta=alt.Theta("absolute_amount:Q", title="Amount"),
            color=alt.Color(
                "driver:N",
                scale=alt.Scale(domain=list(DRIVER_COLORS), range=list(DRIVER_COLORS.values())),
                legend=alt.Legend(title="Driver"),
            ),
            tooltip=["driver", "direction", "amount:Q"],
        )
        .properties(height=285)
    )
    st.altair_chart(themed_chart(chart), use_container_width=True)


def render_weekly_driver_bars(forecast: Forecast) -> None:
    df = weekly_driver_frame(forecast)
    if df.empty:
        alert_box("No weekly driver values to chart.")
        return
    chart = (
        alt.Chart(df)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X("week:N", title="Week"),
            y=alt.Y("value:Q", title="Cash impact"),
            color=alt.Color(
                "driver:N",
                scale=alt.Scale(domain=list(DRIVER_COLORS), range=list(DRIVER_COLORS.values())),
                legend=alt.Legend(title="Driver"),
            ),
            tooltip=["week", "driver", "value:Q"],
        )
        .properties(height=300)
    )
    st.altair_chart(themed_chart(chart), use_container_width=True)


def render_wip_bar(projects: List[Project]) -> None:
    rows = []
    for opco in sorted({project.opco for project in projects}):
        opco_projects = [project for project in projects if project.opco == opco]
        rows.append(
            {
                "opco": opco,
                "WIP": sum(project.wip_to_date for project in opco_projects),
                "Contract value": sum(project.contract_value for project in opco_projects),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        alert_box("No project WIP available.")
        return
    long = df.melt(id_vars=["opco"], var_name="metric", value_name="amount")
    chart = (
        alt.Chart(long)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("opco:N", title="Operating company"),
            y=alt.Y("amount:Q", title="EUR"),
            color=alt.Color("metric:N", scale=alt.Scale(range=[BRAND_GREEN, BRAND_NAVY])),
            tooltip=["opco", "metric", "amount:Q"],
        )
        .properties(height=300)
    )
    st.altair_chart(themed_chart(chart), use_container_width=True)


def render_project_map(projects: List[Project], weather_shift: Dict[str, int]) -> Optional[str]:
    rows = project_map_rows(projects, weather_shift)
    if not rows:
        alert_box("No project locations available for the map.")
        return None

    df = pd.DataFrame(rows)
    center_lat = float(df["lat"].mean())
    center_lon = float(df["lon"].mean())
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        id="projects",
        get_position="[lon, lat]",
        get_radius="radius",
        get_fill_color="color",
        pickable=True,
        auto_highlight=True,
    )
    map_style = (
        "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
        if st.session_state.get("theme_mode") == "Dark Mode"
        else "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
    )
    deck = pdk.Deck(
        map_style=map_style,
        initial_view_state=pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=6.2, pitch=0),
        layers=[layer],
        tooltip={
            "html": (
                "<b>{project_id}</b><br/>{opco}<br/>Risk: {risk}<br/>"
                "WIP: EUR {wip}<br/>Weather shift: {shift} days"
            ),
            "style": {"backgroundColor": "#143B5A", "color": "white"},
        },
    )

    event = None
    try:
        event = st.pydeck_chart(
            deck,
            use_container_width=True,
            height=430,
            key="opco_project_map",
            on_select="rerun",
            selection_mode="single-object",
        )
    except TypeError:
        st.pydeck_chart(deck, use_container_width=True)

    return selected_project_from_map(event)


def selected_project_from_map(event) -> Optional[str]:
    if event is None:
        return None
    selection = getattr(event, "selection", None)
    if selection is None:
        return None
    if hasattr(selection, "to_dict"):
        selection = selection.to_dict()
    objects = selection.get("objects") if isinstance(selection, dict) else None
    if isinstance(objects, dict):
        for value in objects.values():
            if value:
                return value[0].get("project_id")
    if isinstance(objects, list) and objects:
        return objects[0].get("project_id")
    return None


def render_traceability(rows: List[Dict[str, object]]) -> None:
    panel_title("Audit Trail / Traceability")
    st.caption("Driver -> assumption -> scenario -> source records")
    if not rows:
        alert_box("No forecast contributions in this week for the selected driver.")
        return

    for row in rows[:5]:
        driver = escape(str(row["driver"]))
        assumptions = escape(str(row["assumptions"]))
        scenario = escape(str(row["scenario"]))
        source_records = escape(str(row["source_records"]))
        value = escape(format_eur(float(row["value"])))
        computation = escape(str(row["computation"]))
        st.markdown(
            f"""
            <div class="trace-card">
                <div class="trace-flow">{driver} &rarr; {assumptions} &rarr; {scenario} &rarr; {source_records}</div>
                <div class="trace-meta">
                    <strong>Value:</strong> {value}<br/>
                    <strong>Computation:</strong> {computation}<br/>
                    <strong>Weather:</strong> {escape(str(row["weather_shift"]))}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    if len(rows) > 5:
        st.caption(f"Showing first 5 trace cards. Full audit table contains {len(rows)} rows.")
    st.dataframe(rows, width="stretch", hide_index=True)


def render_cfo_tab(forecast: Forecast, transactions_by_id: Dict[str, Transaction]) -> None:
    cash_in, cash_out, net_cash = cash_totals(forecast)
    ending_cash = forecast.running_balance()[-1]

    cols = st.columns(4)
    with cols[0]:
        html_card("Cash in", format_eur(cash_in), "13-week inflows")
    with cols[1]:
        html_card("Cash out", format_eur(abs(cash_out)), "Committed outflows")
    with cols[2]:
        html_card("Net cash", format_eur(net_cash), "Scenario movement")
    with cols[3]:
        html_card("Ending cash", format_eur(ending_cash), "End of horizon")

    render_covenant_panel(forecast, "Covenant health")

    chart_cols = st.columns([2, 1])
    with chart_cols[0]:
        panel_title("13-week cash profile")
        render_cash_chart(forecast)
    with chart_cols[1]:
        panel_title("Driver mix")
        render_driver_donut(forecast)

    panel_title("Driver timing by week")
    render_weekly_driver_bars(forecast)

    panel_title("Forecast table")
    st.dataframe(build_week_rows(forecast), width="stretch", hide_index=True)

    week_options = {f"W{index} - {week.isoformat()}": index for index, week in enumerate(forecast.weeks)}
    drill_cols = st.columns([1, 1])
    selected_week_label = drill_cols[0].selectbox("Trace week", list(week_options), key="cfo_trace_week")
    selected_week = week_options[selected_week_label]
    active_drivers = [
        driver for driver, values in forecast.drivers().items()
        if any(abs(value) > 0.5 for value in values)
    ]
    driver_options = ["All drivers"] + [DRIVER_LABELS.get(driver, driver) for driver in active_drivers]
    selected_driver_label = drill_cols[1].selectbox("Trace driver", driver_options, key="cfo_trace_driver")
    selected_driver = None
    if selected_driver_label != "All drivers":
        selected_driver = next(
            driver for driver in active_drivers
            if DRIVER_LABELS.get(driver, driver) == selected_driver_label
        )
    render_traceability(trace_rows(forecast, selected_week, transactions_by_id, selected_driver))


def render_opco_tab(
    projects: List[Project],
    weather_shift: Dict[str, int],
    forecast: Forecast,
) -> None:
    if not projects:
        alert_box("No project records are loaded. Add project data to populate this view.")
        return

    total_wip = sum(project.wip_to_date for project in projects)
    high_risk = sum(1 for project in projects if risk_level(project, weather_shift)[0] == "High")
    shifted = len(weather_shift)

    cols = st.columns(4)
    with cols[0]:
        html_card("Projects", f"{len(projects)}", "Forward pipeline")
    with cols[1]:
        html_card("WIP exposure", format_eur(total_wip), "All opcos")
    with cols[2]:
        html_card("High risk", f"{high_risk}", "Weather / WIP flags")
    with cols[3]:
        html_card("Shifted projects", f"{shifted}", "Selected scenario")

    map_cols = st.columns([1.45, 1])
    with map_cols[0]:
        panel_title("Mapbox project map")
        st.caption("Click a marker to inspect project risk. Locations are mapped to the operating-company towns in the repo.")
        clicked_project = render_project_map(projects, weather_shift)

    project_rows = project_map_rows(projects, weather_shift)
    project_ids = [row["project_id"] for row in project_rows]
    default_index = project_ids.index(clicked_project) if clicked_project in project_ids else 0

    with map_cols[1]:
        panel_title("Project inspector")
        selected_project_id = st.selectbox(
            "Project",
            project_ids,
            index=default_index,
            key="opco_project_inspector",
        )
        row = next(item for item in project_rows if item["project_id"] == selected_project_id)
        html_card("Risk", str(row["risk"]), str(row["risk_reason"]))
        st.metric("WIP", format_eur(float(row["wip"])))
        st.metric("Contract value", format_eur(float(row["contract_value"])))
        st.metric("Weather exposure", f"{float(row['weather_exposure']):.0%}")
        st.metric("Scenario shift", format_days(int(row["shift"])))

    chart_cols = st.columns([1, 1])
    with chart_cols[0]:
        panel_title("WIP and contract value by opco")
        render_wip_bar(projects)
    with chart_cols[1]:
        panel_title("Driver mix")
        render_driver_donut(forecast)

    panel_title("Project risk table")
    risk_rows = [
        {
            "project": project.project_id,
            "opco": project.opco,
            "customer": project.customer,
            "risk": risk_level(project, weather_shift)[0],
            "wip": round(project.wip_to_date, 2),
            "contract_value": round(project.contract_value, 2),
            "weather_exposure": round(project.weather_exposure, 2),
            "shift": format_days(weather_shift.get(project.project_id, 0)),
        }
        for project in projects
    ]
    st.dataframe(risk_rows, width="stretch", hide_index=True)

    panel_title("Scenario-shifted milestones")
    shifted_rows = shifted_milestone_rows(projects, weather_shift)
    if shifted_rows:
        st.dataframe(shifted_rows, width="stretch", hide_index=True)
    else:
        alert_box("No explicit weather-dependent milestones are shifted in this scenario.")


def render_project_lead_tab(
    projects: List[Project],
    transactions: List[Transaction],
    forecast: Forecast,
    weather_shift: Dict[str, int],
) -> None:
    if not projects:
        alert_box("No project records are loaded. Add project data to populate this view.")
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
    next_milestone = next((milestone for milestone in milestones if milestone.status != "paid"), None)

    cols = st.columns(4)
    with cols[0]:
        html_card("Project", project.project_id, project.opco)
    with cols[1]:
        html_card("WIP", format_eur(project.wip_to_date), f"{project.percent_complete:.0%} complete")
    with cols[2]:
        html_card("Exposure", f"{project.weather_exposure:.0%}", "Weather sensitivity")
    with cols[3]:
        html_card("Weather shift", format_days(project_shift), "Selected scenario")

    if next_milestone:
        scenario_date = next_milestone.planned_date + timedelta(days=project_shift if next_milestone.weather_dependent else 0)
        panel_title("Next invoiceable milestone")
        milestone_cols = st.columns(4)
        milestone_cols[0].metric("Milestone", next_milestone.description)
        milestone_cols[1].metric("Amount", format_eur(next_milestone.amount))
        milestone_cols[2].metric("Planned date", next_milestone.planned_date.isoformat())
        milestone_cols[3].metric("Scenario date", scenario_date.isoformat())
        if project_shift > 0 and next_milestone.weather_dependent:
            alert_box(
                "Weather delays this milestone. Billing and collections move later through the payment-lag driver.",
                tone="warning",
            )
        elif project_shift < 0 and next_milestone.weather_dependent:
            alert_box("Dry weather pulls this milestone earlier, improving collection timing.", tone="success")
        else:
            alert_box("No weather delay is applied to this milestone in the selected scenario.")

    panel_title("Project cash events")
    events = project_contribution_rows(forecast, transactions, project.project_id)
    if events:
        event_df = pd.DataFrame(events)
        chart = (
            alt.Chart(event_df)
            .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
            .encode(
                x=alt.X("week:N", title="Week"),
                y=alt.Y("value:Q", title="Cash impact"),
                color=alt.Color("driver:N", scale=alt.Scale(range=list(DRIVER_COLORS.values()))),
                tooltip=["week", "driver", "value:Q", "assumptions"],
            )
            .properties(height=300)
        )
        st.altair_chart(themed_chart(chart), use_container_width=True)
        st.dataframe(events, width="stretch", hide_index=True)
    else:
        alert_box("No forecast cash events for this project land inside the 13-week horizon.")


def render_board_tab(
    forecast: Forecast,
    base_forecast: Forecast,
    projects: List[Project],
    weather_shift: Dict[str, int],
) -> None:
    render_covenant_panel(forecast, "Consolidated covenant")

    cash_in, cash_out, net_cash = cash_totals(forecast)
    ending_cash = forecast.running_balance()[-1]
    at_risk = sum(1 for project in projects if risk_level(project, weather_shift)[0] == "High")

    cols = st.columns(4)
    with cols[0]:
        html_card("Ending cash", format_eur(ending_cash), "Portfolio")
    with cols[1]:
        html_card("Cash in", format_eur(cash_in), "13-week inflows")
    with cols[2]:
        html_card("Cash out", format_eur(abs(cash_out)), "13-week outflows")
    with cols[3]:
        html_card("High-risk projects", str(at_risk), "Opco risk flags")

    chart_cols = st.columns([1.25, 1])
    with chart_cols[0]:
        panel_title("Board cash trajectory")
        render_cash_chart(forecast)
    with chart_cols[1]:
        panel_title("Portfolio driver mix")
        render_driver_donut(forecast)

    panel_title("Scenario movement vs base")
    movers = biggest_movers(base_forecast, forecast, top=7)
    if movers:
        mover_df = pd.DataFrame(
            [
                {
                    "week": f"W{mover.week}",
                    "driver": DRIVER_LABELS.get(mover.driver, mover.driver),
                    "base": mover.base_value,
                    "scenario": mover.scenario_value,
                    "delta": mover.delta,
                }
                for mover in movers
            ]
        )
        chart = (
            alt.Chart(mover_df)
            .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
            .encode(
                x=alt.X("delta:Q", title="Delta vs base"),
                y=alt.Y("driver:N", sort="-x", title="Driver"),
                color=alt.condition("datum.delta >= 0", alt.value(BRAND_GREEN), alt.value(BRAND_RED)),
                tooltip=["week", "driver", "base:Q", "scenario:Q", "delta:Q"],
            )
            .properties(height=300)
        )
        st.altair_chart(themed_chart(chart), use_container_width=True)
        st.dataframe(mover_df, width="stretch", hide_index=True)
    else:
        alert_box("No scenario movement versus base.")


def main() -> None:
    st.set_page_config(
        page_title="Altis Groep - Weather-Aware Forecast",
        page_icon=None,
        layout="wide",
    )
    theme_mode = st.sidebar.selectbox(
        "Theme",
        ["Light Mode", "Dark Mode"],
        key="theme_mode",
    )
    inject_styles(theme_mode)
    render_sidebar_logo()

    st.sidebar.markdown('<div class="side-section">Data</div>', unsafe_allow_html=True)
    data_mode = st.sidebar.selectbox(
        "Data mode",
        ["Real data", "Demo stub data"],
        key="data_mode",
    )

    transactions_path = ""
    projects_path = ""
    if data_mode == "Real data":
        st.sidebar.caption("Loads reconciled transactions and the revenue-calibrated project pipeline.")
        with st.sidebar.expander("Advanced data files"):
            transactions_path = sidebar_path_picker(
                "transactions",
                TRANSACTION_SUFFIXES,
                "transactions",
                prefer="transactions.csv",
            )
            projects_path = sidebar_path_picker(
                "P&L JSON",
                PROJECT_SUFFIXES,
                "projects",
                prefer="Portfolio",
            )

    state = load_dashboard_state(data_mode, transactions_path, projects_path)
    transactions = state.transactions
    projects = state.projects
    forecasts = state.forecasts
    transactions_by_id = {txn.record_id: txn for txn in transactions}

    st.sidebar.markdown('<div class="side-section">Scenario</div>', unsafe_allow_html=True)
    selected_label = st.sidebar.selectbox("Scenario", list(SCENARIOS), key="scenario")
    scenario_name, scenario_note = SCENARIOS[selected_label]
    weather_shift = state.weather_shifts.get(selected_label, {})
    forecast = forecasts[selected_label]
    base_forecast = forecasts["Base"]

    alert_box(scenario_note, container=st.sidebar)
    exposed = [project.project_id for project in weather_exposed_projects(projects)]
    if not exposed:
        alert_box(
            "No weather-exposed projects are loaded. Wet/dry scenarios will not move timing.",
            tone="warning",
            container=st.sidebar,
        )
    elif weather_shift:
        st.sidebar.caption(f"Shifted projects: {', '.join(sorted(weather_shift))}")
        st.sidebar.caption(f"Weather shift: {format_shift(weather_shift)}")
    else:
        st.sidebar.caption(f"Weather-exposed projects: {', '.join(sorted(exposed))}")
        st.sidebar.caption("Weather shift: none for base")

    st.sidebar.markdown('<div class="side-section">Status</div>', unsafe_allow_html=True)
    if state.using_stub and data_mode == "Real data":
        alert_box(state.data_note, tone="warning", container=st.sidebar)
    elif state.using_stub:
        alert_box(state.data_note, container=st.sidebar)
    else:
        alert_box(state.data_note, tone="success", container=st.sidebar)
    st.sidebar.caption(f"Engine scenario: {scenario_name}")
    st.sidebar.caption(f"Forecast scope: {', '.join(state.opco_forecasts.get(selected_label, {}).keys())}")

    if state.transaction_summary:
        with st.sidebar.expander("Load summary"):
            st.write(state.transaction_summary)
    if state.build_notes:
        with st.sidebar.expander("Build notes"):
            for note in state.build_notes:
                st.write(note)

    render_hero(data_mode, selected_label, state)

    cfo_tab, opco_tab, project_tab, board_tab, mapping_tab = st.tabs(
        ["CFO", "Opco MD", "Project Lead", "PE Board", "GL Mapping"]
    )

    with cfo_tab:
        render_cfo_tab(forecast, transactions_by_id)

    with opco_tab:
        render_opco_tab(projects, weather_shift, forecast)

    with project_tab:
        render_project_lead_tab(projects, transactions, forecast, weather_shift)

    with board_tab:
        render_board_tab(forecast, base_forecast, projects, weather_shift)

    with mapping_tab:
        # Default to the instant keyless heuristic so the app loads fast (Streamlit
        # runs every tab's code on each rerun). OpenAI is one click away in the
        # panel's engine dropdown, and cached after the first call.
        render_mapping_review(default_backend="heuristic")


if __name__ == "__main__":
    main()
