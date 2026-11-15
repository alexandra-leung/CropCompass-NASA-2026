"""Unit helpers for M3.

The farmer thinks in millimetres of water per season (the unit FAO-56 uses);
M4's contract stores the irrigation budget in cubic metres. 1 mm over 1 ha = 10 m3.
"""

from __future__ import annotations

M3_PER_MM_PER_HA = 10.0


def mm_to_m3(depth_mm: float | None, area_ha: float | None) -> float | None:
    """Convert an irrigation depth (mm) over a field area (ha) to a volume (m3).

    Returns None when either input is unknown: a missing value is never defaulted.
    """
    if depth_mm is None or area_ha is None:
        return None
    if depth_mm < 0 or area_ha <= 0:
        raise ValueError("depth_mm must be >= 0 and area_ha must be > 0")
    return round(depth_mm * area_ha * M3_PER_MM_PER_HA, 3)


def m3_to_mm(volume_m3: float | None, area_ha: float | None) -> float | None:
    """Convert an irrigation volume (m3) to a depth (mm) over a field area (ha)."""
    if volume_m3 is None or area_ha is None:
        return None
    if volume_m3 < 0 or area_ha <= 0:
        raise ValueError("volume_m3 must be >= 0 and area_ha must be > 0")
    return round(volume_m3 / (area_ha * M3_PER_MM_PER_HA), 3)
