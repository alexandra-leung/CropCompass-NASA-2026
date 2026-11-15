
from agricultureM2.rotation_water_comparison import (
    compare_rotation_water,
)

result = compare_rotation_water(
    daily_et0_mm=4.0,
    field_area_ha=1.0,
)

print("\nCROPCOMPASS — ROTATION WATER COMPARISON")
print("=" * 55)

for rotation in result["rotations"]:

    print("\n", rotation["rotation_name"])

    print(
        "Total growing days:",
        rotation["total_growth_days"],
    )

    print(
        "Crop evapotranspiration:",
        rotation["total_etc_mm"],
        "mm",
    )

    print(
        "Gross crop water volume:",
        rotation["gross_crop_water_volume_m3"],
        "m3",
    )

    print(
        "Average ETc per day:",
        rotation["average_etc_mm_per_day"],
        "mm/day",
    )

    for crop in rotation["crops"]:
        print(
            " -",
            crop["crop_id"],
            ":",
            crop["etc_mm"],
            "mm",
        )

print("\nLimitations:")
for limitation in result["limitations"]:
    print("-", limitation)

assert len(result["rotations"]) == 3
assert all(
    rotation["total_etc_mm"] > 0
    for rotation in result["rotations"]
)

print("\nTEST PASSED: Three rotations calculated.")
