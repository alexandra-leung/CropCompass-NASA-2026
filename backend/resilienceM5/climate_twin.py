"""Reproducible climate analog rankings; not crop recommendations."""
from __future__ import annotations

import asyncio
import math
from statistics import pstdev

from .scenario_engine import (CANDIDATE_SITES, DataUnavailable, MonthlyClimate,
                              PowerClient, SCENARIOS, get_farm_climate)


def compare_climates(
    target: MonthlyClimate,
    candidates: list[tuple[dict, MonthlyClimate]],
    top_k: int = 3,
) -> list[dict]:
    if len(candidates) < 3:
        raise DataUnavailable("At least three complete NASA candidate records are required")
    if not 1 <= top_k <= len(candidates):
        raise ValueError("top_k must not exceed the number of valid candidates")
    if len({site["id"] for site, _ in candidates}) != len(candidates):
        raise ValueError("Candidate IDs must be unique")
    temp_scale = [
        max(1.0, pstdev([climate.temperature_c[month] for _, climate in candidates]))
        for month in range(12)
    ]
    precip_scale = [
        max(25.0, pstdev([climate.precipitation_mm[month] for _, climate in candidates]))
        for month in range(12)
    ]
    ranked: list[tuple[float, str, dict]] = []
    for site, climate in candidates:
        tz = [
            (target.temperature_c[month] - climate.temperature_c[month]) / temp_scale[month]
            for month in range(12)
        ]
        pz = [
            (target.precipitation_mm[month] - climate.precipitation_mm[month])
            / precip_scale[month]
            for month in range(12)
        ]
        td = sum(x * x for x in tz) / 12
        pd = sum(x * x for x in pz) / 12
        distance = math.sqrt(0.5 * td + 0.5 * pd)
        result = {
            "location": site,
            "distance_index": round(distance, 6),
            "temperature_rmse_c": round(
                math.sqrt(
                    sum(
                        (target.temperature_c[month] - climate.temperature_c[month]) ** 2
                        for month in range(12)
                    )
                    / 12
                ),
                3,
            ),
            "precipitation_mae_mm_per_month": round(
                sum(
                    abs(target.precipitation_mm[month] - climate.precipitation_mm[month])
                    for month in range(12)
                )
                / 12,
                3,
            ),
            "temperature_distance_component": round(td, 6),
            "precipitation_distance_component": round(pd, 6),
            "monthly_comparison": [
                {
                    "month": month + 1,
                    "future_t_c": target.temperature_c[month],
                    "candidate_t_c": climate.temperature_c[month],
                    "future_p_mm": target.precipitation_mm[month],
                    "candidate_p_mm": climate.precipitation_mm[month],
                }
                for month in range(12)
            ],
            "candidate_provenance": climate.provenance,
        }
        ranked.append((distance, site["id"], result))
    return [
        result
        for _, _, result in sorted(ranked, key=lambda item: (item[0], item[1]))[:top_k]
    ]


async def find_climate_twins(
    latitude: float,
    longitude: float,
    scenario: str,
    start_year: int,
    end_year: int,
    top_k: int = 3,
    client: PowerClient | None = None,
) -> dict:
    if scenario not in SCENARIOS:
        raise ValueError(f"Unsupported M1 scenario: {scenario}")
    if not 2027 <= start_year <= end_year <= 2100:
        raise ValueError("Future period must be within 2027–2100 and start_year <= end_year")
    if end_year - start_year + 1 > 30:
        raise ValueError("Future period may not exceed 30 years")

    client = client or PowerClient()
    historical, target = await get_farm_climate(
        latitude, longitude, scenario, start_year, end_year
    )
    candidate_semaphore = asyncio.Semaphore(3)

    async def acquire_candidate(site: dict) -> tuple[dict, MonthlyClimate | None, str | None]:
        try:
            async with candidate_semaphore:
                climate = await client.historical_async(site["latitude"], site["longitude"])
            return site, climate, None
        except DataUnavailable as exc:
            return site, None, str(exc)

    candidate_results = await asyncio.gather(
        *(acquire_candidate(site) for site in CANDIDATE_SITES)
    )
    candidates = [
        (site, climate)
        for site, climate, _ in candidate_results
        if climate is not None
    ]
    excluded = [
        {"site_id": site["id"], "reason": error}
        for site, climate, error in candidate_results
        if climate is None
    ]
    if len(candidates) < max(3, top_k):
        exclusion_details = "; ".join(
            f"{item['site_id']}: {item['reason']}" for item in excluded
        )
        raise DataUnavailable(
            f"Only {len(candidates)} valid NASA POWER candidates are available; "
            f"at least {max(3, top_k)} are required. "
            f"Excluded candidates: {exclusion_details or 'no details supplied'}"
        )
    ranked = compare_climates(target, candidates, top_k)
    return {
        "field": {"latitude": latitude, "longitude": longitude},
        "scenario": scenario, "period": {"start_year": start_year, "end_year": end_year},
        "historical": historical.to_dict(), "projected_target": target.to_dict(),
        "analogs": ranked, "candidate_count": len(candidates), "excluded_candidates": excluded,
        "method": {
            "name": "Calendar-month weighted standardized Euclidean distance",
            "temperature_weight": 0.5, "precipitation_weight": 0.5,
            "formula": "sqrt(0.5 * mean(((Tf-Tc)/stdT)^2) + 0.5 * mean(((Pf-Pc)/stdP)^2))",
            "standardization": (
                "Per-month population standard deviation across valid candidate climates; "
                "1 degC and 25 mm/month scale floors prevent zero variance"
            ),
            "candidate_pool": (
                f"Limited pool of {len(CANDIDATE_SITES)} documented reference locations; "
                "not a global search"
            ),
            "interpretation": "Lower index means more similar within this candidate pool; not a probability",
        },
        "limitations": [
            "Climate matching does not establish soil, pest, water availability, management or crop suitability",
            "All climate records are regional gridded evidence rather than a field sensor",
            "Future target is a NASA bias-corrected/downscaled multi-model CMIP6 mean, not a deterministic weather forecast",
            "Model spread is descriptive disagreement, not a probability interval",
        ],
    }
