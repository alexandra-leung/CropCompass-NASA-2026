
import asyncio
import calendar
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
                    })

    if not rows:
        raise ValueError(
            f"No usable {variable} observations in NASA response"
        )

    print(f"[CALENDAR] {variable}: {time_calendar}")
    
    return rows


async def _fetch_variable(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    model: dict[str, Any],
    scenario: str,
    year: int,
    variable: str,
    source: dict[str, Any],
) -> list[dict[str, Any]]:

    model_id = model["id"]
    variant = model["variant"]
    dataset_version = source.get("version", "unknown")

    cache_key = (
        f"nex:{dataset_version}:calendar-v2:{model_id}:{variant}:"
        f"{scenario}:{year}:{variable}"
    )

    cached = get_cached(cache_key)
    if cached is not None:
        return cached["rows"]

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
            "north": "-19.5",
            "south": "-21.0",
            "west": "56.8",
            "east": "58.2",
            "horizStride": "1",
            "time_start": f"{year}-01-01T12:00:00Z",
            "time_end": f"{year}-12-31T12:00:00Z",
            "accept": "netcdf3",
            "addLatLon": "true",
        }

        try:
            async with semaphore:
                response = await client.get(url, params=params)

            if response.status_code == 404:
                errors.append(f"{filename}: HTTP 404")
                continue

            response.raise_for_status()

            rows = _parse_netcdf(response.content, variable)

            save_cached(cache_key, {"rows": rows})
            return rows

        except Exception as exc:
            errors.append(f"{filename}: {exc}")

            # Try another filename suffix only after a 404.
            if "HTTP 404" not in str(exc):
                break

    # Use expired cached data if NASA is temporarily unavailable.
    stale = get_cached(cache_key, allow_stale=True)
    if stale is not None:
        return stale["rows"]

    raise RuntimeError(
        f"Unable to retrieve {variable} for {model_id}, "
        f"{scenario}, {year}. {'; '.join(errors)}"
    )

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
