"""Weather -> schedule model (validated against Dutch standards).

VALIDATED FORM (see altis_weather_model_validation.md): NOT a linear "days lost
per mm" slope. Dutch construction runs on a THRESHOLD / binary "unworkable day"
(onwerkbare dag) model with legally-defined triggers, calibrated per calendar
quarter to KNMI norms, with a roofing-specific severity uplift.

Anchors (so this reads as a regulated input, not a guess):
  - CAO Onwerkbaar weer Bouw & Infra / UAV 2012 §42: a workday is unworkable when
    it rains >= 5h (300 min) in 07:00-19:00, when CAO frost/wind-chill norms are
    met, or when >= 5h of work is impossible. Whole days only.
  - KNMI De Bilt 1991-2020 climate normals for base frequencies, by calendar
    quarter (frost is almost entirely a Q1/Q4 phenomenon).
  - Roofing is ~1.5-2x more weather-exposed than general construction (bonded
    membranes need a dry, frost-free deck; decks linger damp after rain).

Two entry points:
  - unworkable_days_from_daily(daily, ...) : apply the thresholds to real
    Open-Meteo daily data (Lane C's live path). Open-Meteo is KEYLESS.
  - scenario_shift(projects, scenario, month) : offline path used by the
    dashboard, using KNMI per-quarter expected unworkable days.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# --- Daily thresholds (proxies for the CAO rules on Open-Meteo daily data) ------
# Roofing loses a day on essentially any measurable rain wetting the deck; we use
# a low mm proxy for "it rained meaningfully during the workday".
RAIN_STOP_MM = 1.0
SIGNIFICANT_RAIN_MM = 5.0     # after this, the deck lingers damp
LINGER_DAYS = 1               # extra unworkable day(s) after significant rain
# CAO frost trigger is ~overnight < -3C (NOT KNMI vorstdag Tmin<=0). Daily proxy:
FROST_STOP_TMIN_C = -3.0
FROST_SEASON_MONTHS = {11, 12, 1, 2, 3}   # CAO winter window 1 Nov - 31 Mar

# Roofing vs general construction (validated range 1.5-2x; top of range, WEAK -
# refine against the opcos' own site logs).
ROOFING_UPLIFT = 2.0
# A lost WORK day delays the schedule by ~1 work day ~= 1.4 calendar days.
WORKDAY_TO_CALENDAR = 1.4

# --- KNMI-calibrated base unworkable days per CALENDAR QUARTER -------------------
# General construction, AFTER applying the CAO thresholds (much lower than KNMI
# vorstdagen). Rain ~19 waiting days/yr (Bouwend Nederland), spread ~evenly; CAO
# frost-unworkable days concentrated in Q1/Q4 and far fewer than vorstdagen.
QUARTER_UNWORKABLE = {1: 9, 2: 4, 3: 6, 4: 8}   # Q1 Jan-Mar ... Q4 Oct-Dec
# Wet/dry = a P90/P10 quarter of that same calendar quarter (not a global swing).
SCENARIO_MULT = {"base": 1.0, "wet-quarter": 1.6, "dry-quarter": 0.45}


@dataclass
class DailyWeather:
    day: date
    precip_mm: float
    temp_min: float


def _quarter(month: int) -> int:
    return (month - 1) // 3 + 1


# --- live path: thresholds on real daily data ----------------------------------

def fetch_daily(lat: float, lon: float, start: date, end: date,
                archive: bool = False, timeout: float = 10.0) -> List[DailyWeather]:
    """Keyless Open-Meteo daily precipitation_sum + temperature_2m_min."""
    base = ARCHIVE_URL if archive else FORECAST_URL
    url = (f"{base}?latitude={lat}&longitude={lon}"
           f"&start_date={start.isoformat()}&end_date={end.isoformat()}"
           f"&daily=precipitation_sum,temperature_2m_min&timezone=Europe%2FAmsterdam")
    with urllib.request.urlopen(url, timeout=timeout) as resp:   # nosec - public API
        data = json.loads(resp.read().decode())
    d = data.get("daily", {})
    days, precip, tmin = d.get("time", []), d.get("precipitation_sum", []), d.get("temperature_2m_min", [])
    out = []
    for i, ds in enumerate(days):
        out.append(DailyWeather(
            day=date.fromisoformat(ds),
            precip_mm=float(precip[i] or 0) if i < len(precip) else 0.0,
            temp_min=float(tmin[i]) if i < len(tmin) and tmin[i] is not None else 99.0))
    return out


def unworkable_days_from_daily(daily: List[DailyWeather], roofing: bool = True) -> int:
    """Count unworkable WORK days by applying the CAO-style thresholds to daily
    weather (skips weekends). Adds lingering days after significant rain."""
    lost, linger = 0, 0
    for d in sorted(daily, key=lambda x: x.day):
        if d.day.weekday() >= 5:
            continue   # Sat/Sun not work days
        stop = False
        if d.precip_mm >= RAIN_STOP_MM:
            stop = True
            if d.precip_mm >= SIGNIFICANT_RAIN_MM and roofing:
                linger = LINGER_DAYS
        elif linger > 0 and roofing:
            stop = True            # deck still damp the day after heavy rain
            linger -= 1
        if d.day.month in FROST_SEASON_MONTHS and d.temp_min <= FROST_STOP_TMIN_C:
            stop = True
        if stop:
            lost += 1
    return round(lost * (ROOFING_UPLIFT if roofing else 1.0))


# --- offline path: KNMI per-quarter expected unworkable days --------------------

def expected_unworkable_days(month: int, scenario: str, exposure: float) -> float:
    """Expected unworkable WORK days for a weather-exposed roofing project over the
    quarter that `month` falls in, under a scenario."""
    base = QUARTER_UNWORKABLE[_quarter(month)]
    mult = SCENARIO_MULT.get(scenario, 1.0)
    return base * mult * ROOFING_UPLIFT * max(0.0, min(exposure, 1.0))


def scenario_shift(projects, scenario: str, month: int = 1) -> Dict[str, int]:
    """The weather handoff: {project_id: calendar-days the schedule slips} RELATIVE
    to base. base -> {}; wet -> positive (later); dry -> negative (earlier).

    `month` is the calendar month the 13-week horizon starts in (drives which
    quarter's KNMI profile applies). Frost-heavy Q1/Q4 produce larger shifts than
    the dry summer quarter - exactly the seasonality the validation calls for.
    """
    if scenario == "base":
        return {}
    out: Dict[str, int] = {}
    for p in projects:
        if p.weather_exposure <= 0:
            continue
        base = expected_unworkable_days(month, "base", p.weather_exposure)
        scen = expected_unworkable_days(month, scenario, p.weather_exposure)
        delta = round((scen - base) * WORKDAY_TO_CALENDAR)
        if delta != 0:
            out[p.project_id] = delta
    return out


def summarise_weather(days: List[DailyWeather], frost_threshold: float = FROST_STOP_TMIN_C):
    """(total rain mm, count of frost-stop days) - for inspection/calibration."""
    rain = sum(d.precip_mm for d in days)
    frost = sum(1 for d in days if d.temp_min <= frost_threshold)
    return rain, frost


def live_unworkable_by_location(locations: Dict[str, tuple], start: date, end: date,
                                roofing: bool = True, timeout: float = 8.0) -> Dict[str, dict]:
    """REAL near-term signal: fetch each opco's Open-Meteo forecast (keyless) and
    score it with the roofing unworkable-day thresholds. Open-Meteo's forecast
    reaches ~16 days, so this informs the near term; the 13-week scenario engine
    runs on KNMI climatology. Returns {name: {unworkable_days, rain_mm, frost_days,
    days}}; locations that fail to fetch are simply omitted (graceful)."""
    out: Dict[str, dict] = {}
    for name, (lat, lon) in locations.items():
        try:
            daily = fetch_daily(lat, lon, start, end, archive=False, timeout=timeout)
        except Exception:
            continue
        if not daily:
            continue
        rain, frost = summarise_weather(daily)
        out[name] = {
            "unworkable_days": unworkable_days_from_daily(daily, roofing=roofing),
            "rain_mm": round(rain, 1),
            "frost_days": frost,
            "days": len(daily),
        }
    return out
