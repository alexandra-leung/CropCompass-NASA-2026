
import asyncio
import calendar
import base64
import logging
import math
import statistics
from datetime import datetime, timezone
from typing import Any

import httpx
import numpy as np
from netCDF4 import Dataset, num2date

from climateM1.core.config import (
    NEX_GDDP_BASE_URL,
    NEX_GDDP_MAX_CONCURRENCY,
)
from climateM1.services.cache import get_cached, save_cached
from climateM1.services.locations import ClimateLocation
from climateM1.services.model_registry import (
    get_enabled_models,
    get_projection_years,
    get_scenarios,
    load_model_registry,
)

logger = logging.getLogger(__name__)


def _nex_units_match(variable: str, units: str) -> bool:
    normalized = " ".join(
        units.lower()
        .replace("−", "-")
        .replace("⁻", "-")
        .replace("²", "2")
        .replace("**", "")
        .replace("^", "")
        .split()
    )
    if variable == "pr":
        return normalized in {
            "kg m-2 s-1",
            "kg/m2/s",
            "kg m-2 sec-1",
        }
    if variable == "tas":
        return normalized in {"k", "kelvin"}
    return False


def _parse_netcdf(content: bytes, variable: str) -> list[dict[str, Any]]:
    rows = []

    with Dataset("inmemory", mode="r", memory=content) as dataset:
        lat_name = next(
            (name for name in ("lat", "latitude") if name in dataset.variables),
            None,
        )
        lon_name = next(
            (name for name in ("lon", "longitude") if name in dataset.variables),
            None,
        )

        if not all(
            (lat_name, lon_name, "time" in dataset.variables,
             variable in dataset.variables)
        ):
            raise ValueError(
                f"NetCDF response is missing coordinates or {variable}"
            )

        lat_var = dataset.variables[lat_name]
        lon_var = dataset.variables[lon_name]
        time_var = dataset.variables["time"]
        data_var = dataset.variables[variable]
        units = str(getattr(data_var, "units", "")).strip()
        if not _nex_units_match(variable, units):
            raise ValueError(
                f"Unexpected NASA NEX {variable} units {units!r}"
            )
        time_calendar = getattr(time_var, "calendar", "standard")

        latitudes = lat_var[:]
        longitudes = lon_var[:]

        times = num2date(
            time_var[:],
            units=time_var.units,
            calendar=getattr(time_var, "calendar", "standard"),
            only_use_cftime_datetimes=False,
        )

        values = np.ma.asarray(data_var[:])
        dimensions = data_var.dimensions

        if len(dimensions) != 3:
            raise ValueError(
                f"Unexpected dimensions for {variable}: {dimensions}"
            )

        time_axis = dimensions.index(time_var.dimensions[0])
        lat_axis = dimensions.index(lat_var.dimensions[0])
        lon_axis = dimensions.index(lon_var.dimensions[0])

        values = np.moveaxis(
            values,
            (time_axis, lat_axis, lon_axis),
            (0, 1, 2),
        )

        for t in range(len(times)):
            for i in range(len(latitudes)):
                for j in range(len(longitudes)):
                    value = values[t, i, j]

                    if np.ma.is_masked(value):
                        continue

                    value = float(value)

                    if not np.isfinite(value):
                        continue

                    rows.append({
                        "time": str(times[t]),
                        "latitude": float(latitudes[i]),
                        "longitude": float(longitudes[j]),
                        "value": value,
                        "calendar": time_calendar,
                        "units": units,
                    })

    if not rows:
        raise ValueError(
            f"No usable {variable} observations in NASA response"
        )

    logger.debug("Parsed %s data using %s calendar", variable, time_calendar)
    
    return rows


def _nex_request_bounds(latitude: float, longitude: float) -> dict[str, str]:
    return {
        "north": f"{min(90.0, latitude + 0.5):.4f}",
        "south": f"{max(-60.0, latitude - 0.5):.4f}",
        "west": f"{max(-180.0, longitude - 0.5):.4f}",
        "east": f"{min(180.0, longitude + 0.5):.4f}",
    }


async def _fetch_variable_record(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    model: dict[str, Any],
    scenario: str,
    year: int,
    variable: str,
    source: dict[str, Any],
    coordinates: tuple[float, float] | None = None,
) -> dict[str, Any]:

    model_id = model["id"]
    variant = model["variant"]
    dataset_version = source.get("version", "unknown")

    if coordinates is None:
        cache_key = (
            f"nex:{dataset_version}:calendar-v2:{model_id}:{variant}:"
            f"{scenario}:{year}:{variable}"
        )
    else:
        latitude, longitude = coordinates
        bounds = _nex_request_bounds(latitude, longitude)
        grid_label = model.get("grid_label", "gn")
        cache_key = (
            f"nex:{dataset_version}:calendar-v3:{model_id}:{variant}:{grid_label}:"
            f"{scenario}:{year}:{variable}:"
            f"{bounds['north']}:{bounds['south']}:{bounds['west']}:{bounds['east']}"
        )

    cached = get_cached(cache_key)
    if cached is not None:
        return {**cached, "cache_status": "fresh_cache"}

    suffixes = source.get("filename_suffixes", ["_v2.0", ""])
    errors = []

    for suffix in suffixes:
        
        grid_label = model.get("grid_label", "gn")

        filename = (
            f"{variable}_day_{model_id}_{scenario}_{variant}_"
            f"{grid_label}_{year}{suffix}.nc"
        )

        url = (
            f"{NEX_GDDP_BASE_URL}/{model_id}/"
            f"{scenario}/{variant}/{variable}/{filename}"
        )

        params = {
            "var": variable,
            "horizStride": "1",
            "time_start": f"{year}-01-01T12:00:00Z",
            "time_end": f"{year}-12-31T12:00:00Z",
            "accept": "netcdf3",
            "addLatLon": "true",
        }
        if coordinates is None:
            params.update({
                "north": "-19.5",
                "south": "-21.0",
                "west": "56.8",
                "east": "58.2",
            })
        else:
            params.update(_nex_request_bounds(*coordinates))

        try:
            async with semaphore:
                response = await client.get(url, params=params)

            if response.status_code == 404:
                errors.append(f"{filename}: HTTP 404")
                continue

            response.raise_for_status()

            rows = _parse_netcdf(response.content, variable)
            record = {
                "rows": rows,
                "units": rows[0]["units"],
                "source_url": str(response.url),
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "source_response_base64": base64.b64encode(response.content).decode("ascii"),
                "model": model_id,
                "variant": variant,
                "grid_label": model.get("grid_label", "gn"),
                "scenario": scenario,
                "year": year,
                "variable": variable,
                "cache_status": "network",
            }
            save_cached(cache_key, record)
            return record

        except Exception as exc:
            errors.append(f"{filename}: {exc}")

            # Try another filename suffix only after a 404.
            if "HTTP 404" not in str(exc):
                break

    # Use expired cached data if NASA is temporarily unavailable.
    stale = get_cached(cache_key, allow_stale=True)
    if stale is not None:
        return {**stale, "cache_status": "stale_cache"}

    raise RuntimeError(
        f"Unable to retrieve {variable} for {model_id}, "
        f"{scenario}, {year}. {'; '.join(errors)}"
    )


async def _fetch_variable(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    model: dict[str, Any],
    scenario: str,
    year: int,
    variable: str,
    source: dict[str, Any],
) -> list[dict[str, Any]]:
    record = await _fetch_variable_record(
        client, semaphore, model, scenario, year, variable, source
    )
    return record["rows"]

def _get_expected_days(year: int, calendar_name: str) -> int:
    calendar_name = calendar_name.lower()

    if calendar_name in ("360_day",):
        return 360

    if calendar_name in ("365_day", "noleap"):
        return 365

    if calendar_name in ("366_day", "all_leap"):
        return 366

    if calendar_name in (
        "standard",
        "gregorian",
        "proleptic_gregorian",
    ):
        return 366 if calendar.isleap(year) else 365

    raise ValueError(
        f"Unsupported climate calendar: {calendar_name}"
    )

async def _build_scenario_value(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    model: dict[str, Any],
    scenario: str,
    year: int,
    location: ClimateLocation,
    source: dict[str, Any],
) -> dict[str, Any]:

    precipitation, temperature = await asyncio.gather(
        _fetch_variable(
            client, semaphore, model, scenario, year, "pr", source
        ),
        _fetch_variable(
            client, semaphore, model, scenario, year, "tas", source
        ),
    )

    temp_by_key = {
        (row["time"], row["latitude"], row["longitude"]): row["value"]
        for row in temperature
    }

    paired = []

    for row in precipitation:
        key = (row["time"], row["latitude"], row["longitude"])
        temp = temp_by_key.get(key)

        if temp is not None:
            paired.append((row, temp))

    if not paired:
        raise ValueError(
            f"No paired precipitation and temperature observations "
            f"for {model['id']} {scenario} {year}"
        )

    nearest = min(
        (pair[0] for pair in paired),
        key=lambda row: (
            abs(row["latitude"] - location.latitude)
            + abs(row["longitude"] - location.longitude)
        ),
    )

    grid_lat = nearest["latitude"]
    grid_lon = nearest["longitude"]

    selected = [
        (rain["time"], rain["value"], temp)
        for rain, temp in paired
        if rain["latitude"] == grid_lat
        and rain["longitude"] == grid_lon
    ]

    # Keep one observation per date.
    daily_values = {
        timestamp: (rain, temp)
        for timestamp, rain, temp in selected
    }

    rainfall_mm = sum(
        rain * 86400
        for rain, _ in daily_values.values()
    )

    temperature_c = (
        sum(temp - 273.15 for _, temp in daily_values.values())
        / len(daily_values)
    )

    calendar_names = {
        row["calendar"] for row in precipitation
    }

    if len(calendar_names) != 1:
        raise ValueError(
            f"Inconsistent precipitation calendars: {calendar_names}"
        )

    calendar_name = calendar_names.pop()

    expected_days = _get_expected_days(year, calendar_name)
    sample_days = len(daily_values)
    missing_days = max(0, expected_days - sample_days)

    return {
        "year": year,
        "rainfallMm": round(rainfall_mm, 1),
        "temperatureC": round(temperature_c, 2),
        "gridCell": {
            "latitude": grid_lat,
            "longitude": grid_lon,
        },
        "sampleDays": sample_days,
        "expectedDays": expected_days,
        "missingDays": missing_days,
        "completenessPct": round(
            sample_days / expected_days * 100, 2
        ),
        "calendar": calendar_name,
    }


async def _build_model_result(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    model: dict[str, Any],
    location: ClimateLocation,
    source: dict[str, Any],
    scenario_definitions: list[dict[str, Any]],
    years: list[int],
) -> dict[str, Any]:

    model_scenarios = []
    errors = []

    for definition in scenario_definitions:
        values = []

        for year in years:
            try:
                value = await _build_scenario_value(
                    client,
                    semaphore,
                    model,
                    definition["id"],
                    year,
                    location,
                    source,
                )
                values.append(value)

            except Exception as exc:
                errors.append(
                    f"{definition['id']} {year}: {str(exc)}"
                )

        model_scenarios.append({
            **definition,
            "model": model["id"],
            "values": values,
        })

    expected_results = len(scenario_definitions) * len(years)
    successful_results = sum(
        len(scenario["values"])
        for scenario in model_scenarios
    )

    if successful_results == expected_results:
        status = "success"
    elif successful_results > 0:
        status = "partial"
    else:
        status = "failed"

    return {
        "id": model["id"],
        "variant": model["variant"],
        "status": status,
        "scenarios": model_scenarios,
        "errors": errors,
    }


def _calculate_statistics(values: list[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "mean": round(statistics.mean(values), 2),
        "median": round(statistics.median(values), 2),
        "minimum": round(min(values), 2),
        "maximum": round(max(values), 2),
        "spread": round(max(values) - min(values), 2),
    }


def _build_ensemble(
    model_results: list[dict[str, Any]],
    scenario_definitions: list[dict[str, Any]],
    years: list[int],
) -> list[dict[str, Any]]:

    ensemble = []

    for definition in scenario_definitions:
        ensemble_values = []

        for year in years:
            contributing = []

            for model in model_results:
                for scenario in model["scenarios"]:
                    if scenario["id"] != definition["id"]:
                        continue

                    for value in scenario["values"]:
                        if value["year"] == year:
                            contributing.append((model["id"], value))

            if not contributing:
                continue

            rainfall_values = [
                value["rainfallMm"]
                for _, value in contributing
            ]

            temperature_values = [
                value["temperatureC"]
                for _, value in contributing
            ]

            ensemble_values.append({
                "year": year,
                "rainfallMm": _calculate_statistics(rainfall_values),
                "temperatureC": _calculate_statistics(
                    temperature_values
                ),
                "contributingModels": [
                    model_id for model_id, _ in contributing
                ],
            })

        ensemble.append({
            **definition,
            "values": ensemble_values,
        })

    return ensemble


async def fetch_scenarios(
    location: ClimateLocation,
) -> dict[str, Any]:

    registry = load_model_registry()
    source = registry["source"]
    models = get_enabled_models()
    scenario_definitions = get_scenarios()
    years = get_projection_years()

    if not models:
        raise ValueError("No climate models are enabled in the registry")

    retrieved_at = datetime.now(timezone.utc).isoformat()
    semaphore = asyncio.Semaphore(NEX_GDDP_MAX_CONCURRENCY)

    limits = httpx.Limits(
        max_connections=NEX_GDDP_MAX_CONCURRENCY,
        max_keepalive_connections=NEX_GDDP_MAX_CONCURRENCY,
    )

    async with httpx.AsyncClient(
        timeout=120.0,
        limits=limits,
    ) as client:

        model_results = await asyncio.gather(
            *[
                _build_model_result(
                    client,
                    semaphore,
                    model,
                    location,
                    source,
                    scenario_definitions,
                    years,
                )
                for model in models
            ]
        )

    successful_models = [
        model for model in model_results
        if model["status"] != "failed"
    ]

    if not successful_models:
        failure_details = "\n".join(
            f"{model['id']}: {' | '.join(model.get('errors', []))}"
            for model in model_results
        )

        raise RuntimeError(
            f"All configured climate models failed to retrieve data. "
            f"Details: {failure_details}"
        )

    ensemble = _build_ensemble(
        model_results,
        scenario_definitions,
        years,
    )

    # Preserve the original scenarios field for existing consumers.
    access_model = next(
        (
            model for model in model_results
            if model["id"] == "ACCESS-CM2"
        ),
        None,
    )

    legacy_scenarios = (
        access_model["scenarios"]
        if access_model is not None
        else []
    )

    has_missing_data = any(
        model["status"] != "success"
        or any(
            value["missingDays"] > 0
            for scenario in model["scenarios"]
            for value in scenario["values"]
        )
        for model in model_results
    )

    failed_models = [
        model["id"]
        for model in model_results
        if model["status"] != "success"
    ]

    caveats = [
        "Precipitation flux (kg m-2 s-1) is converted to daily millimetres by multiplying by 86,400, then summed annually.",
        "Temperature is converted from Kelvin to degrees Celsius.",
        "Ensemble spread is the difference between the highest and lowest contributing model values; it is not a probability interval.",
        "The nearest 0.25-degree grid cell represents regional climate conditions, not an exact field-level forecast.",
    ]

    if failed_models:
        caveats.append(
            "Some models were unavailable or incomplete: "
            + ", ".join(failed_models)
        )

    return {
        "locationId": location.id,
        "baselinePeriod": (
            "Projected annual values for "
            + ", ".join(map(str, years))
            + "; not a field-level forecast"
        ),
        "scenarios": legacy_scenarios,
        "modelResults": model_results,
        "ensemble": ensemble,
        "provenance": {
            "source": "NASA NEX-GDDP-CMIP6",
            "product": "Daily downscaled CMIP6 projections",
            "variable": "pr + tas",
            "model": "Multi-model ensemble",
            "coordinates": {
                "latitude": location.latitude,
                "longitude": location.longitude,
            },
            "gridResolution": "0.25° × 0.25° (~25 km)",
            "dateRange": ", ".join(map(str, years)),
            "missingData": has_missing_data,
            "retrievedAt": retrieved_at,
            "caveat": (
                "Model outputs are sampled at their nearest grid cells. "
                "They are regional projections, not field-level forecasts."
            ),
        },
        "caveats": caveats,
    }


def _expected_month_days(year: int, month: int, calendar_name: str) -> int:
    normalized = calendar_name.lower()
    if normalized == "360_day":
        return 30
    if normalized in ("365_day", "noleap"):
        return (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[month - 1]
    if normalized in ("366_day", "all_leap"):
        return (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[month - 1]
    if normalized in ("standard", "gregorian", "proleptic_gregorian"):
        return calendar.monthrange(year, month)[1]
    raise ValueError(f"Unsupported climate calendar: {calendar_name}")


def _longitude_distance(left: float, right: float) -> float:
    return abs((left - right + 180.0) % 360.0 - 180.0)


def _grid_distance_km(
    left_latitude: float,
    left_longitude: float,
    right_latitude: float,
    right_longitude: float,
) -> float:
    latitude_delta = math.radians(right_latitude - left_latitude)
    longitude_delta = math.radians(
        _longitude_distance(right_longitude, left_longitude)
    )
    left_radians = math.radians(left_latitude)
    right_radians = math.radians(right_latitude)
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(left_radians)
        * math.cos(right_radians)
        * math.sin(longitude_delta / 2) ** 2
    )
    return 12742.0 * math.asin(min(1.0, math.sqrt(haversine)))


def _aggregate_projection_year(
    precipitation: list[dict[str, Any]],
    temperature: list[dict[str, Any]],
    latitude: float,
    longitude: float,
    year: int,
) -> dict[str, Any]:
    temp_by_key = {
        (row["time"], row["latitude"], row["longitude"]): row
        for row in temperature
    }
    paired = [
        (rain, temp_by_key[(rain["time"], rain["latitude"], rain["longitude"])])
        for rain in precipitation
        if (rain["time"], rain["latitude"], rain["longitude"]) in temp_by_key
    ]
    if not paired:
        raise ValueError(f"No paired precipitation/temperature values for {year}")
    if any(not _nex_units_match("pr", str(row.get("units", ""))) for row, _ in paired):
        raise ValueError(f"NASA NEX precipitation units are missing or inconsistent for {year}")
    if any(not _nex_units_match("tas", str(row.get("units", ""))) for _, row in paired):
        raise ValueError(f"NASA NEX temperature units are missing or inconsistent for {year}")

    nearest_rain, _ = min(
        paired,
        key=lambda pair: (
            _grid_distance_km(
                latitude,
                longitude,
                pair[0]["latitude"],
                pair[0]["longitude"],
            ),
            pair[0]["latitude"],
            pair[0]["longitude"],
        ),
    )
    grid_latitude = nearest_rain["latitude"]
    grid_longitude = nearest_rain["longitude"]
    selected = [
        (rain, temp)
        for rain, temp in paired
        if rain["latitude"] == grid_latitude
        and rain["longitude"] == grid_longitude
    ]
    calendars = {
        row["calendar"]
        for pair in selected
        for row in pair
    }
    if len(calendars) != 1:
        raise ValueError(f"Inconsistent calendars for {year}: {sorted(calendars)}")
    calendar_name = calendars.pop()

    daily: dict[tuple[int, int, int], tuple[float, float]] = {}
    for rain, temp in selected:
        date_text = rain["time"][:10]
        try:
            row_year, month, day = (int(value) for value in date_text.split("-"))
            rain_rate = float(rain["value"])
            temperature_k = float(temp["value"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid NASA NEX daily value for {year}: {rain['time']}") from exc
        if row_year != year or not (1 <= month <= 12) or not math.isfinite(rain_rate) or not math.isfinite(temperature_k):
            raise ValueError(f"Invalid NASA NEX daily value for {year}: {rain['time']}")
        if rain_rate < 0:
            raise ValueError(f"Negative precipitation from NASA NEX for {rain['time']}")
        key = (row_year, month, day)
        if key in daily:
            raise ValueError(f"Duplicate NASA NEX daily value for {rain['time']}")
        daily[key] = (rain_rate, temperature_k)

    expected_dates = {
        (year, month, day)
        for month in range(1, 13)
        for day in range(1, _expected_month_days(year, month, calendar_name) + 1)
    }
    if set(daily) != expected_dates:
        missing_days = len(expected_dates - set(daily))
        extra_days = len(set(daily) - expected_dates)
        raise ValueError(
            f"Incomplete or invalid NASA NEX daily period for {year}: "
            f"{missing_days} missing and {extra_days} unexpected dates"
        )

    monthly_temperature = []
    monthly_precipitation = []
    for month in range(1, 13):
        days = _expected_month_days(year, month, calendar_name)
        month_rows = [
            daily[(year, month, day)]
            for day in range(1, days + 1)
            if (year, month, day) in daily
        ]
        if len(month_rows) != days:
            raise ValueError(
                f"Incomplete NASA NEX period for {year}-{month:02d}: "
                f"received {len(month_rows)} of {days} daily values"
            )
        monthly_temperature.append(
            statistics.fmean(value[1] - 273.15 for value in month_rows)
        )
        monthly_precipitation.append(
            sum(value[0] * 86400.0 for value in month_rows)
        )

    return {
        "temperature_c": monthly_temperature,
        "precipitation_mm": monthly_precipitation,
        "calendar": calendar_name,
        "grid_cell": {
            "latitude": grid_latitude,
            "longitude": grid_longitude,
        },
    }


async def fetch_monthly_projection(
    latitude: float,
    longitude: float,
    scenario: str,
    start_year: int,
    end_year: int,
) -> dict[str, Any]:
    """Fetch raw M1 NEX daily records and aggregate a monthly CMIP6 ensemble."""
    if not -60 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("Coordinates must be valid latitude/longitude values")
    if not 2027 <= start_year <= end_year <= 2100:
        raise ValueError("Projection period must be within 2027–2100 and start_year <= end_year")
    if end_year - start_year + 1 > 30:
        raise ValueError("Projection periods may not exceed 30 years")

    scenario_definitions = get_scenarios()
    if scenario not in {definition["id"] for definition in scenario_definitions}:
        raise ValueError(
            f"Unsupported M1 scenario {scenario!r}; configured scenarios are "
            f"{sorted(definition['id'] for definition in scenario_definitions)}"
        )

    registry = load_model_registry()
    models = get_enabled_models()
    if not models:
        raise ValueError("No climate models are enabled in the M1 registry")
    source = registry["source"]
    semaphore = asyncio.Semaphore(NEX_GDDP_MAX_CONCURRENCY)
    limits = httpx.Limits(
        max_connections=NEX_GDDP_MAX_CONCURRENCY,
        max_keepalive_connections=NEX_GDDP_MAX_CONCURRENCY,
    )

    async def model_series(model: dict[str, Any]) -> dict[str, Any]:
        yearly_values = []
        source_records = []
        try:
            for year in range(start_year, end_year + 1):
                precipitation_record, temperature_record = await asyncio.gather(
                    _fetch_variable_record(
                        client, semaphore, model, scenario, year, "pr", source,
                        coordinates=(latitude, longitude),
                    ),
                    _fetch_variable_record(
                        client, semaphore, model, scenario, year, "tas", source,
                        coordinates=(latitude, longitude),
                    ),
                )
                yearly_values.append(
                    _aggregate_projection_year(
                        precipitation_record["rows"],
                        temperature_record["rows"],
                        latitude,
                        longitude,
                        year,
                    )
                )
                source_records.append({
                    "year": year,
                    "precipitation_url": precipitation_record.get("source_url"),
                    "precipitation_retrieved_at": precipitation_record.get("retrieved_at"),
                    "temperature_url": temperature_record.get("source_url"),
                    "temperature_retrieved_at": temperature_record.get("retrieved_at"),
                    "precipitation_cache_status": precipitation_record.get("cache_status"),
                    "temperature_cache_status": temperature_record.get("cache_status"),
                    "precipitation_input_units": precipitation_record.get("units"),
                    "temperature_input_units": temperature_record.get("units"),
                    "grid_cell": yearly_values[-1]["grid_cell"],
                    "calendar": yearly_values[-1]["calendar"],
                })
        except Exception as exc:
            return {
                "id": model["id"],
                "variant": model["variant"],
                "grid_label": model.get("grid_label", "gn"),
                "status": "failed",
                "error": str(exc),
                "source_records": source_records,
            }

        return {
            "id": model["id"],
            "variant": model["variant"],
            "grid_label": model.get("grid_label", "gn"),
            "status": "success",
            "temperature_c": [
                statistics.fmean(values["temperature_c"][month] for values in yearly_values)
                for month in range(12)
            ],
            "precipitation_mm": [
                statistics.fmean(values["precipitation_mm"][month] for values in yearly_values)
                for month in range(12)
            ],
            "grid_cells": sorted(
                {
                    (value["grid_cell"]["latitude"], value["grid_cell"]["longitude"])
                    for value in yearly_values
                }
            ),
            "source_records": source_records,
        }

    async with httpx.AsyncClient(
        timeout=120.0,
        limits=limits,
    ) as client:
        model_results = await asyncio.gather(
            *(model_series(model) for model in models)
        )

    successful_models = [
        result for result in model_results if result["status"] == "success"
    ]
    if len(successful_models) < 3:
        errors = [
            f"{result['id']}: {result.get('error', 'incomplete data')}"
            for result in model_results
            if result["status"] != "success"
        ]
        raise RuntimeError(
            "Fewer than three complete M1 climate models are available for the "
            f"requested period. {'; '.join(errors)}"
        )

    uncertainty = []
    for month in range(12):
        temperatures = [result["temperature_c"][month] for result in successful_models]
        precipitation_values = [
            result["precipitation_mm"][month] for result in successful_models
        ]
        uncertainty.append({
            "month": month + 1,
            "temperature_min_c": round(min(temperatures), 4),
            "temperature_max_c": round(max(temperatures), 4),
            "temperature_spread_c": round(max(temperatures) - min(temperatures), 4),
            "precipitation_min_mm": round(min(precipitation_values), 4),
            "precipitation_max_mm": round(max(precipitation_values), 4),
            "precipitation_spread_mm": round(
                max(precipitation_values) - min(precipitation_values), 4
            ),
            "contributing_models": len(successful_models),
        })

    source_urls = sorted({
        url
        for result in successful_models
        for record in result["source_records"]
        for url in (
            record["precipitation_url"],
            record["temperature_url"],
        )
        if url
    })
    retrieved_at = max(
        timestamp
        for result in successful_models
        for record in result["source_records"]
        for timestamp in (
            record["precipitation_retrieved_at"],
            record["temperature_retrieved_at"],
        )
        if timestamp
    )
    failed_models = [
        {"id": result["id"], "variant": result["variant"], "error": result["error"]}
        for result in model_results
        if result["status"] != "success"
    ]
    return {
        "temperature_c": [
            round(
                statistics.fmean(result["temperature_c"][month] for result in successful_models),
                4,
            )
            for month in range(12)
        ],
        "precipitation_mm": [
            round(
                statistics.fmean(result["precipitation_mm"][month] for result in successful_models),
                4,
            )
            for month in range(12)
        ],
        "temperature_unit": "degC",
        "precipitation_unit": "mm/month",
        "provenance": {
            "source": "NASA NEX-GDDP-CMIP6",
            "source_id": "NASA NEX-GDDP-CMIP6",
            "product": "Daily downscaled CMIP6 projections",
            "dataset_version": source.get("version", "unknown"),
            "source_urls": source_urls,
            "retrieved_at": retrieved_at,
            "data_type": "bias_corrected_climate_projection",
            "scenario": scenario,
            "model": "multi-model ensemble",
            "model_series": [
                {
                    "id": result["id"],
                    "variant": result["variant"],
                    "grid_label": result["grid_label"],
                    "temperature_c": result["temperature_c"],
                    "precipitation_mm": result["precipitation_mm"],
                    "grid_cells": result["grid_cells"],
                    "source_records": result["source_records"],
                }
                for result in successful_models
            ],
            "excluded_models": failed_models,
            "requested_coordinates": {
                "latitude": latitude,
                "longitude": longitude,
            },
            "grid_resolution": "0.25° × 0.25° nominal",
            "period_start": f"{start_year}-01",
            "period_end": f"{end_year}-12",
            "temperature_unit": "degC",
            "precipitation_unit": "mm/month",
            "temperature_method": (
                "Daily tas in kelvin converted to degC; monthly daily means "
                "averaged across years, then equally averaged across models"
            ),
            "precipitation_method": (
                "Daily pr in kg m-2 s-1 multiplied by 86,400 to obtain mm/day, "
                "summed within each month, averaged across years per model, then "
                "equally averaged across contributing models"
            ),
            "climate_adjustment": (
                "NASA NEX-GDDP-CMIP6 is bias-corrected and downscaled; "
                "M1/M5 apply no additional delta adjustment"
            ),
            "model_uncertainty": uncertainty,
            "missing_data": bool(failed_models),
            "requested_model_count": len(models),
            "model_coverage_pct": round(
                len(successful_models) / len(models) * 100, 2
            ),
            "cache_status": "M1 NEX source records",
            "limitations": [
                "Model spread is a descriptive range, not a probability interval",
                "Grid-cell projections are regional, not field-level forecasts",
            ],
        },
    }
