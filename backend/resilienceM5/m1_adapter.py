"""Adapt M1's source-backed monthly climate services to the M5 climate type."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from climateM1.services.history import fetch_monthly_history
from climateM1.services.projections import fetch_monthly_projection

from .scenario_engine import DataUnavailable, HIST_START, HIST_END, MonthlyClimate


def _to_monthly_climate(record: dict[str, Any]) -> MonthlyClimate:
    if record.get("temperature_unit") != "degC":
        raise DataUnavailable("M1 temperature values are not in degC")
    if record.get("precipitation_unit") != "mm/month":
        raise DataUnavailable("M1 precipitation values are not monthly totals in mm/month")
    provenance = record.get("provenance")
    source_urls = provenance.get("source_urls") if isinstance(provenance, dict) else None
    if not isinstance(source_urls, list) or not source_urls or any(
        not isinstance(url, str) or not url.strip() for url in source_urls
    ):
        raise DataUnavailable("M1 climate response has no source URL provenance")
    try:
        temperature = tuple(float(value) for value in record["temperature_c"])
        precipitation = tuple(float(value) for value in record["precipitation_mm"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DataUnavailable("M1 climate response has invalid monthly values") from exc
    try:
        return MonthlyClimate(temperature, precipitation, provenance)
    except ValueError as exc:
        raise DataUnavailable(f"M1 monthly climate values are invalid: {exc}") from exc


def _validate_m1_provenance(
    climate: MonthlyClimate,
    source: str,
    latitude: float,
    longitude: float,
    start: str,
    end: str,
    scenario: str | None,
) -> None:
    provenance = climate.provenance
    expected_coordinates = {"latitude": latitude, "longitude": longitude}
    if provenance.get("source") != source:
        raise DataUnavailable(f"M1 returned unexpected source identity: {provenance.get('source')!r}")
    if provenance.get("requested_coordinates") != expected_coordinates:
        raise DataUnavailable("M1 source coordinates do not match the requested farm location")
    if provenance.get("period_start") != start or provenance.get("period_end") != end:
        raise DataUnavailable("M1 source period does not match the requested climate period")
    if provenance.get("scenario") != scenario:
        raise DataUnavailable("M1 source scenario does not match the requested SSP")

    expected_host = (
        "power.larc.nasa.gov"
        if source == "NASA POWER"
        else "ds.nccs.nasa.gov"
    )
    for source_url in provenance["source_urls"]:
        parsed_url = urlparse(source_url)
        if parsed_url.scheme != "https" or parsed_url.hostname != expected_host:
            raise DataUnavailable(f"M1 returned a non-NASA or unexpected source URL: {source_url}")

    if source == "NASA NEX-GDDP-CMIP6":
        if provenance.get("data_type") != "bias_corrected_climate_projection":
            raise DataUnavailable("M1 future climate classification is not the expected NASA NEX product")
        adjustment = provenance.get("climate_adjustment")
        if not isinstance(adjustment, str) or "no additional delta adjustment" not in adjustment:
            raise DataUnavailable("M1 future climate adjustment status is missing or unexpected")
        model_series = provenance.get("model_series")
        uncertainty = provenance.get("model_uncertainty")
        if (
            not isinstance(model_series, list)
            or len(model_series) < 3
            or any(
                not isinstance(model, dict)
                or not model.get("id")
                or not model.get("variant")
                for model in model_series
            )
        ):
            raise DataUnavailable("M1 future climate does not include at least three model series")
        if not isinstance(uncertainty, list) or len(uncertainty) != 12:
            raise DataUnavailable("M1 future climate is missing monthly model uncertainty")


async def provide_m1_climate(
    latitude: float,
    longitude: float,
    scenario: str,
    start_year: int,
    end_year: int,
) -> tuple[MonthlyClimate, MonthlyClimate]:
    try:
        history_record = await fetch_monthly_history(
            latitude,
            longitude,
            HIST_START,
            HIST_END,
        )
    except (RuntimeError, ValueError) as exc:
        raise DataUnavailable(f"M1 historical climate is unavailable or incomplete: {exc}") from exc

    try:
        projection_record = await fetch_monthly_projection(
            latitude,
            longitude,
            scenario,
            start_year,
            end_year,
        )
    except RuntimeError as exc:
        raise DataUnavailable(f"M1 future climate is unavailable or incomplete: {exc}") from exc

    historical = _to_monthly_climate(history_record)
    future = _to_monthly_climate(projection_record)
    _validate_m1_provenance(
        historical,
        "NASA POWER",
        latitude,
        longitude,
        f"{HIST_START}-01",
        f"{HIST_END}-12",
        None,
    )
    _validate_m1_provenance(
        future,
        "NASA NEX-GDDP-CMIP6",
        latitude,
        longitude,
        f"{start_year}-01",
        f"{end_year}-12",
        scenario,
    )
    return historical, future
