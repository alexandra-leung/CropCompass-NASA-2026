
from agricultureM2.water_wallet import load_coefficients

crops = [
    "maize",
    "tomato",
    "onion",
    "cabbage",
    "cowpea",
    "groundnut",
    "sweet_potato",
]

print("\nCROPCOMPASS — CROP DATA VERIFICATION\n")

for crop in crops:
    coefficients, source = load_coefficients(crop)

    total_days = sum(
        int(coefficients[key])
        for key in [
            "days_initial",
            "days_development",
            "days_mid",
            "days_late",
        ]
    )

    print(f"Crop: {crop}")
    print(f"Growth duration: {total_days} days")
    print(f"Kc initial: {coefficients['kc_initial']}")
    print(f"Kc mid: {coefficients['kc_mid']}")
    print(f"Kc end: {coefficients['kc_end']}")
    print(f"Reference: {source}")
    print("-" * 50)

print("\nAll seven crop records loaded successfully.")
