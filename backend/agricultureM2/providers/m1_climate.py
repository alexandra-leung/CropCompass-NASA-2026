
import os
from datetime import date

import httpx


DEFAULT_M1_URL = "http://127.0.0.1:8000"


class ClimateProviderError(RuntimeError):
    pass


def get_m1_base_url():
    return os.getenv(
        "M1_API_BASE_URL",
        DEFAULT_M1_URL,
    ).rstrip("/")


def fetch_m1_data(
    endpoint: str,
    params: dict,
    base_url: str | None = None,
):
    """
    Retrieve an actual M1 API response.

    No synthetic fallback.
    No fabricated climate values.
    """

    url = (
        base_url or get_m1_base_url()
    ).rstrip("/") + endpoint

    try:
        with httpx.Client(
            timeout=90.0,
            follow_redirects=True,
        ) as client:
            response = client.get(
                url,
                params=params,
            )

            response.raise_for_status()
            payload = response.json()

    except (
        httpx.HTTPError,
        ValueError,
    ) as exc:
        raise ClimateProviderError(
            f"M1 climate request failed: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise ClimateProviderError(
            "M1 returned an unexpected response type."
        )

    return {
        "data": payload,
        "provenance": {
            "provider": "CropCompass M1",
            "upstream": "NASA climate products",
            "request_url": str(response.url),
            "synthetic": False,
        },
    }


def get_climate_history(
    location_id: str,
    start: date | None = None,
    end: date | None = None,
    base_url: str | None = None,
):
    params = {
        "location_id": location_id,
    }

    if start is not None:
        params["start"] = start.isoformat()

    if end is not None:
        params["end"] = end.isoformat()

    return fetch_m1_data(
        "/api/climate/history",
        params,
        base_url,
    )


def get_climate_scenarios(
    location_id: str,
    base_url: str | None = None,
):
    return fetch_m1_data(
        "/api/climate/scenarios",
        {"location_id": location_id},
        base_url,
    )
