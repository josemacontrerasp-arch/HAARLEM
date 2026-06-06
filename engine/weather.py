"""Weather chain helper (Lane C's lane, written so they can drop it in).

Open-Meteo needs **NO API KEY** — free, keyless, no signup. This turns rain/frost
into the `{project_id: working_days_lost}` dict the engine consumes, using the
interpretable coefficients from engine/learn.py.

Pipeline:
  fetch_daily(lat, lon, start, end)            # keyless Open-Meteo, stdlib only
    -> summarise_weather(...)                  # rain_mm, frost_days
    -> learn.predict_days_lost(rain, frost, coeffs)
    -> {project_id: days_lost} per scenario    # -> build_forecast(weather_shift=...)

Network is optional: if the call fails (sandbox/offline), callers can pass a
cached JSON or use scenario_shift() with default intensities.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

from .learn import Coefficient, WeatherObs, predict_days_lost

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Default interpretable coefficients (override with learn.estimate_weather_coeffs
# on real Open-Meteo history). Roofing rule-of-thumb: heavy rain / frost stop work.
DEFAULT_COEFFS: Dict[str, Coefficient] = {
    "rain": Coefficient("days_lost_per_mm_rain", 0.04, "days/mm", 0),
    "frost": Coefficient("days_lost_per_frost_day", 0.8, "days/frost-day", 0),
}

# Scenario intensity over a quarter (~13 weeks) — rough Dutch climate baselines.
SCENARIO_WEATHER = {
    "base":        {"rain_mm": 180, "frost_days": 4},
    "wet-quarter": {"rain_mm": 320, "frost_days": 9},
    "dry-quarter": {"rain_mm": 90,  "frost_days": 1},
}


@dataclass
class DailyWeather:
    day: date
    precip_mm: float
    temp_min: float


def fetch_daily(lat: float, lon: float, start: date, end: date,
                archive: bool = False, timeout: float = 10.0) -> List[DailyWeather]:
    """Keyless Open-Meteo daily prec: precipitation_sum + temperature_2m_min."""
    base = ARCHIVE_URL if archive else FORECAST_URL
    url = (f"{base}?latitude={lat}&longitude={lon}"
           f"&start_date={start.isoformat()}&end_date={end.isoformat()}"
           f"&daily=precipitation_sum,temperature_2m_min&timezone=Europe%2FAmsterdam")
    with urllib.request.urlopen(url, timeout=timeout) as resp:   # nosec - public API
        data = json.loads(resp.read().decode())
    return _parse(data)


def _parse(data: dict) -> List[DailyWeather]:
    d = data.get("daily", {})
    days = d.get("time", [])
    precip = d.get("precipitation_sum", [])
    tmin = d.get("temperature_2m_min", [])
    out = []
    for i, ds in enumerate(days):
        out.append(DailyWeather(
            day=date.fromisoformat(ds),
            precip_mm=float(precip[i] or 0) if i < len(precip) else 0.0,
            temp_min=float(tmin[i]) if i < len(tmin) and tmin[i] is not None else 99.0,
        ))
    return out


def summarise_weather(days: List[DailyWeather], frost_threshold: float = 0.0):
    """Aggregate daily rows -> (rain_mm total, frost_days count)."""
    rain = sum(d.precip_mm for d in days)
    frost = sum(1 for d in days if d.temp_min <= frost_threshold)
    return rain, frost


def days_lost_for_projects(
    projects, rain_mm: float, frost_days: float,
    coeffs: Optional[Dict[str, Coefficient]] = None,
) -> Dict[str, int]:
    """Scale the base days-lost by each project's weather_exposure (0..1)."""
    coeffs = coeffs or DEFAULT_COEFFS
    base_loss = predict_days_lost(rain_mm, frost_days, coeffs)
    out: Dict[str, int] = {}
    for p in projects:
        if p.weather_exposure > 0:
            out[p.project_id] = round(base_loss * p.weather_exposure)
    return out


def scenario_shift(projects, scenario: str,
                   coeffs: Optional[Dict[str, Coefficient]] = None) -> Dict[str, int]:
    """The whole weather handoff in one call: scenario -> {project_id: days_lost}.

    Uses SCENARIO_WEATHER intensities (no network). For real weather, fetch_daily
    + summarise_weather first, then days_lost_for_projects. dry-quarter pulls
    earlier (negative shift) relative to base.
    """
    w = SCENARIO_WEATHER.get(scenario, SCENARIO_WEATHER["base"])
    loss = days_lost_for_projects(projects, w["rain_mm"], w["frost_days"], coeffs)
    if scenario == "dry-quarter":
        base = days_lost_for_projects(projects, SCENARIO_WEATHER["base"]["rain_mm"],
                                      SCENARIO_WEATHER["base"]["frost_days"], coeffs)
        return {pid: loss.get(pid, 0) - base.get(pid, 0) for pid in base}  # negative
    if scenario == "base":
        return {}
    # wet-quarter: extra days lost vs base
    base = days_lost_for_projects(projects, SCENARIO_WEATHER["base"]["rain_mm"],
                                  SCENARIO_WEATHER["base"]["frost_days"], coeffs)
    return {pid: loss.get(pid, 0) - base.get(pid, 0) for pid in loss}
