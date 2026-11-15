from agricultureM2.water_wallet import load_coefficients


def test_load_coefficients_reads_backend_reference_data():
    coefficients, source = load_coefficients("maize")

    assert coefficients["kc_initial"] == 0.3
    assert source.startswith("https://")
