"""Soil inputs for a farm.

Every soil value carries where it came from, so M4 can show it honestly:
  - "farmer"       : typed or confirmed by the farmer
  - "map_estimate" : read from a soil map (e.g. SoilGrids), not tested on the field
  - "unknown"      : not provided; stays null and becomes a blind spot in M4
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

SoilTexture = Literal["sand", "loamy_sand", "sandy_loam", "loam", "clay_loam", "clay", "unknown"]
Drainage = Literal["poor", "moderate", "good", "unknown"]
SoilSource = Literal["farmer", "map_estimate", "unknown"]

TEXTURE_LABELS: dict[str, str] = {
    "sand": "Sand",
    "loamy_sand": "Loamy sand",
    "sandy_loam": "Sandy loam",
    "loam": "Loam",
    "clay_loam": "Clay loam",
    "clay": "Clay",
    "unknown": "Unknown",
}


class SoilInputs(BaseModel):
    texture: SoilTexture = "unknown"
    texture_source: SoilSource = "unknown"
    ph: float | None = Field(default=None, ge=0, le=14)
    ph_source: SoilSource = "unknown"
    drainage: Drainage = "unknown"
    drainage_source: SoilSource = "unknown"

    @model_validator(mode="after")
    def _source_matches_value(self) -> "SoilInputs":
        # A value that is unknown cannot claim a source, and a known value needs one.
        if self.texture == "unknown":
            self.texture_source = "unknown"
        elif self.texture_source == "unknown":
            raise ValueError("soil.texture_source is required when texture is given")
        if self.ph is None:
            self.ph_source = "unknown"
        elif self.ph_source == "unknown":
            raise ValueError("soil.ph_source is required when ph is given")
        if self.drainage == "unknown":
            self.drainage_source = "unknown"
        elif self.drainage_source == "unknown":
            raise ValueError("soil.drainage_source is required when drainage is given")
        return self

    def confidence(self) -> Literal["farmer_confirmed", "map_estimate", "partial", "unknown"]:
        sources = {self.texture_source, self.ph_source, self.drainage_source}
        if sources == {"unknown"}:
            return "unknown"
        if sources == {"farmer"}:
            return "farmer_confirmed"
        if "unknown" in sources:
            return "partial"
        return "farmer_confirmed" if sources <= {"farmer"} else "map_estimate"

    def missing(self) -> list[str]:
        out = []
        if self.texture == "unknown":
            out.append("soil.texture")
        if self.ph is None:
            out.append("soil.ph")
        if self.drainage == "unknown":
            out.append("soil.drainage")
        return out
