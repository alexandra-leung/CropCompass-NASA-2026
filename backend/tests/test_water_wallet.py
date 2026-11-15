import math

import pytest

from agricultureM2.water_wallet import (
    calculate_crop_water_demand,
    load_coefficients,
)


def test_load_coefficients_reads_backend_reference_data():
    coefficients, source = load_coefficients("maize")

    assert coefficients["kc_initial"] == 0.3
    assert source.startswith("https://")


def test_crop_water_demand_reports_etc_not_irrigation_requirement():
    result = calculate_crop_water_demand("maize", [1.0] * 125)

    assert result["growth_days"] == 125
    assert result["crop_evapotranspiration_mm"] == 107.4
    assert result["irrigation_requirement_mm"] is None
    assert result["coefficient_source"].startswith("https://")


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf, True])
def test_crop_water_demand_rejects_nonfinite_or_boolean_et0(invalid):
    with pytest.raises(ValueError, match="finite, nonnegative"):
        calculate_crop_water_demand("maize", [invalid] * 125)
