from datetime import date, datetime, timedelta, timezone
from typing import Any
import numpy as np
import pandas as pd
import httpx
from climateM1.core.config import NASA_POWER_BASE_URL
from climateM1.models.climate import HistoryResponse
from climateM1.services.locations import ClimateLocation
import pymannkendall as mk
from scipy.stats import theilslopes


def _longest_dry_spell(daily_values: list[tuple[date, float]]) -> int:
    longest = current = 0
    previous_day: date | None = None
    for day, rainfall in daily_values:
        if previous_day is not None and day != previous_day + timedelta(days=1):
            longest = max(longest, current)
            current = 0
        if rainfall < 1.0:
            current += 1
        else:
            longest = max(longest, current)
            current = 0
        previous_day = day
    return max(longest, current)


def _season(month: int) -> str:
    if month in (12, 1, 2): return "DJF"
    if month in (3, 4, 5): return "MAM"
    if month in (6, 7, 8): return "JJA"
    return "SON"

def _calculate_trend(years: list[int], values: list[float]) -> dict[str, Any]:
    if len(values) < 3:
        return {
            "direction": "no trend",
            "slope": 0.0,
            "pValue": 1.0,
            "significant": False,
            "observations": len(values),
        }

    # Mann-Kendall test: detect trend direction and significance
    result = mk.original_test(values)

    # Theil-Sen estimator: calculate the rate of change per year
    slope, intercept, low, high = theilslopes(values, years)

    return {
        "direction": result.trend,
        "slope": round(float(slope), 4),
        "pValue": round(float(result.p), 4),
        "significant": bool(result.p < 0.05),
        "observations": len(values),
    }

def normalize_power_history(raw: dict[str, Any], location: ClimateLocation, start: str, end: str, retrieved_at: str) -> dict[str, Any]:
    parameters = raw.get("properties", {}).get("parameter", {})
    rainfall = parameters.get("PRECTOTCORR", {})
    temperature = parameters.get("T2M", {})
    if not rainfall or not temperature:
        raise ValueError("NASA POWER returned no precipitation or temperature observations")

    start_day = date(int(start[:4]), int(start[4:6]), int(start[6:8]))
    end_day = date(int(end[:4]), int(end[4:6]), int(end[6:8]))
    expected_days = (end_day - start_day).days + 1
    fill_value = raw.get("header", {}).get("fill_value", -999)
    daily: list[tuple[date, float, float]] = []
    for date_key in sorted(set(rainfall) | set(temperature)):
        try:
            day = date(int(date_key[:4]), int(date_key[4:6]), int(date_key[6:8]))
            rain = float(rainfall.get(date_key, fill_value))
            temp = float(temperature.get(date_key, fill_value))
        except (TypeError, ValueError):
            continue
        if start_day <= day <= end_day and rain != fill_value and temp != fill_value and np.isfinite(rain) and np.isfinite(temp):
            daily.append((day, rain, temp))
    if len(daily) < 30:
        raise ValueError("NASA POWER returned fewer than 30 valid daily observations")

    # Use a DataFrame for deterministic calendar grouping; December belongs to
    # the following DJF season year (e.g. Dec 2021 + Jan/Feb 2022 = 2022-DJF).
    frame = pd.DataFrame(daily, columns=["day", "rainfall", "temperature"])
    frame["day"] = pd.to_datetime(frame["day"])
    frame["year"] = frame["day"].dt.year
    frame["season"] = frame["day"].dt.month.map(_season)
    frame["season_year"] = frame["year"] + (frame["day"].dt.month == 12).astype(int)

    years: dict[int, list[tuple[date, float, float]]] = {}
    seasons: dict[str, list[tuple[date, float, float]]] = {}
    for year, group in frame.groupby("year", sort=True):
        years[int(year)] = [(row.day.date(), float(row.rainfall), float(row.temperature)) for row in group.itertuples()]
    for (season_year, season_name), group in frame.groupby(["season_year", "season"], sort=True):
        period = f"{int(season_year)}-{season_name}"
        seasons[period] = [(row.day.date(), float(row.rainfall), float(row.temperature)) for row in group.itertuples()]

    def build_point(period: str, rows: list[tuple[date, float, float]]) -> dict[str, Any]:
        rain_days = [(row[0], row[1]) for row in rows]
        return {
            "period": period,
            "label": period,
            "rainfallMm": round(sum(row[1] for row in rows), 1),
            "temperatureC": round(sum(row[2] for row in rows) / len(rows), 2),
            "drySpellDays": _longest_dry_spell(rain_days),
        }

    timeseries = [build_point(str(year), rows) for year, rows in sorted(years.items())]

    # Include complete and incomplete meteorological seasons.
    seasonal = []

    for period, rows in sorted(seasons.items()):
        season_year, season_name = period.split("-")
        year = int(season_year)

        # Determine the full calendar range of the season.
        if season_name == "DJF":
            season_start = date(year - 1, 12, 1)
            season_end = date(year, 3, 1) - timedelta(days=1)
        elif season_name == "MAM":
            season_start = date(year, 3, 1)
            season_end = date(year, 6, 1) - timedelta(days=1)
        elif season_name == "JJA":
            season_start = date(year, 6, 1)
            season_end = date(year, 9, 1) - timedelta(days=1)
        else:  # SON
            season_start = date(year, 9, 1)
            season_end = date(year, 12, 1) - timedelta(days=1)

        season_expected_days = (season_end - season_start).days + 1
        observed_days = len({day for day, _, _ in rows})
        completeness_pct = min(100.0, observed_days / season_expected_days * 100)

        point = build_point(period, rows)
        point["completenessPct"] = round(completeness_pct, 1)
        point["completenessStatus"] = (
            "complete" if completeness_pct == 100 else "incomplete"
        )
        seasonal.append(point)

    trend_years = [int(point["period"]) for point in timeseries]

    rainfall_values = [point["rainfallMm"] for point in timeseries]
    temperature_values = [point["temperatureC"] for point in timeseries]

    annual_rainfall_trend = _calculate_trend(
        trend_years, rainfall_values
    )

    annual_temperature_trend = _calculate_trend(
        trend_years, temperature_values
    )

    # Keep the existing metric temporarily for compatibility
    temperature_trend = annual_temperature_trend["slope"]
    first_rain = timeseries[0]["rainfallMm"]
    last_rain = timeseries[-1]["rainfallMm"]
    rainfall_shift = ((last_rain - first_rain) / first_rain * 100) if first_rain else 0.0
    completeness = min(100.0, len(daily) / expected_days * 100)
    longest_dry = max((point["drySpellDays"] for point in timeseries), default=0)
    base = {
        "source": "NASA POWER",
        "product": "Daily meteorology",
        "coordinates": {"latitude": location.latitude, "longitude": location.longitude},
        "gridResolution": "0.5° × 0.625° (POWER daily point product; grid support varies by variable)",
        "dateRange": f"{start_day.isoformat()} → {end_day.isoformat()}",
        "missingData": len(daily) < expected_days,
        "retrievedAt": retrieved_at,
    }
    print("DEBUG METRICS:", {
        "annualRainfallTrend": annual_rainfall_trend,
        "annualTemperatureTrend": annual_temperature_trend,
    })
    return HistoryResponse.model_validate({
        "location": {   
            "id": location.id,
            "name": location.name,
            "district": location.district,
            "country": "Mauritius",
        },
        "units": {
            "rainfall": "mm",
            "temperature": "°C daily mean",
            "drySpells": "consecutive days with rainfall < 1 mm/day",
        },
        "timeseries": timeseries,
        "seasonal": seasonal,
        "metrics": {
            "rainfallShift": round(rainfall_shift, 1),
            "temperatureTrend": round(temperature_trend, 3),
            "longestDrySpell": longest_dry,
            "dataCompleteness": round(completeness, 1),
            "annualRainfallTrend": annual_rainfall_trend,
            "annualTemperatureTrend": annual_temperature_trend,
        },
        "provenance": [
            {**base, "variable": "PRECTOTCORR"},
            {**base, "variable": "T2M"},
        ],
    }).model_dump(by_alias=True)


async def fetch_history(location: ClimateLocation, start: str, end: str) -> dict[str, Any]:
    params = {
        "parameters": "PRECTOTCORR,T2M",
        "community": "AG",
        "longitude": location.longitude,
        "latitude": location.latitude,
        "start": start,
        "end": end,
        "format": "JSON",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(NASA_POWER_BASE_URL, params=params)
        response.raise_for_status()
        return normalize_power_history(response.json(), location, start, end, datetime.now(timezone.utc).isoformat())
