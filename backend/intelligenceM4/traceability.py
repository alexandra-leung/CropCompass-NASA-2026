"""
Field-path resolution shared by the Evidence Passport and Blind-Spot Detector.

A field_path is a dotted/indexed path into an AnalysisBundle serialised by
alias (i.e. the JSON the API exchanges), e.g.
    climate.scenarios.ensemble[1].values[2].rainfallMm.mean
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from intelligenceM4.schemas import UPSTREAM_MODULES, BlindSpot

_TOKEN = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


class TraceabilityError(RuntimeError):
    """A cited value does not match the bundle field it points to."""


def resolve_field_path(data: Any, path: str) -> Any:
    current = data
    for key, index in _TOKEN.findall(path):
        current = current[int(index)] if index else current[key]
    return current


def check_value(bundle_json: dict[str, Any], label: str, value: Any,
                field_path: str | None) -> None:
    try:
        resolved = resolve_field_path(bundle_json, field_path or "")
    except (KeyError, IndexError, TypeError) as exc:
        raise TraceabilityError(f"{label}: field_path '{field_path}' does not exist") from exc
    if resolved != value:
        raise TraceabilityError(
            f"{label}: value {value!r} != bundle value {resolved!r} at '{field_path}'")


def verify_citations(blind_spots: Iterable[BlindSpot], bundle_json: dict[str, Any]) -> None:
    for spot in blind_spots:
        for citation in spot.citations:
            if citation.source_module in UPSTREAM_MODULES:
                check_value(bundle_json, f"{spot.code}/{citation.label}",
                            citation.value, citation.field_path)
