"""Phase 1 — M4 providers: thin service-layer adapters that never raise.

Network-free by default: M1 service functions are monkeypatched to return the
REAL fixture payloads (or to fail). Set M4_LIVE=1 to also run live M1 calls.
"""

import asyncio
import copy
import os
import sys
import types

import pytest

from intelligenceM4.fixtures import load_fixture
from intelligenceM4.providers import (
    agriculture_provider,
    climate_provider,
    farm_provider,
    resilience_provider,
)
from intelligenceM4.schemas import M2RotationResult, ScenarioResponse

SCENARIOS = "m1_scenarios__pamplemousses-04.json"
HISTORY = "m1_history__pamplemousses-04.json"


def run(coro):
    return asyncio.run(coro)


def patch_m1(monkeypatch, name, fn):
    import climateM1.services.history as history
    import climateM1.services.projections as projections

    module = projections if name == "fetch_scenarios" else history
    monkeypatch.setattr(module, name, fn)


# ---------------------------------------------------------------------------
# M1
# ---------------------------------------------------------------------------

def test_scenarios_ok_from_real_payload(monkeypatch):
    async def fake(location):
        assert location.id == "pamplemousses-04"
        return load_fixture(SCENARIOS)

    patch_m1(monkeypatch, "fetch_scenarios", fake)
    result = run(climate_provider.get_scenarios("pamplemousses-04"))
    assert result.status == "ok"
    assert isinstance(result.data, ScenarioResponse)
    assert result.called == "climateM1.services.projections.fetch_scenarios"


def test_scenarios_partial_when_m1_flags_missing_data(monkeypatch):
    payload = copy.deepcopy(load_fixture(SCENARIOS))
    payload["provenance"]["missingData"] = True

    async def fake(location):
        return payload

    patch_m1(monkeypatch, "fetch_scenarios", fake)
    assert run(climate_provider.get_scenarios("pamplemousses-04")).status == "partial"


def test_scenarios_partial_when_a_model_failed(monkeypatch):
    payload = copy.deepcopy(load_fixture(SCENARIOS))
    payload["modelResults"][0]["status"] = "failed"

    async def fake(location):
        return payload

    patch_m1(monkeypatch, "fetch_scenarios", fake)
    assert run(climate_provider.get_scenarios("pamplemousses-04")).status == "partial"


def test_scenarios_exception_becomes_unavailable(monkeypatch):
    async def boom(location):
        raise RuntimeError("All configured climate models failed")

    patch_m1(monkeypatch, "fetch_scenarios", boom)
    result = run(climate_provider.get_scenarios("pamplemousses-04"))
    assert result.status == "unavailable"
    assert result.data is None
    assert "RuntimeError" in result.error


def test_scenarios_timeout_becomes_unavailable(monkeypatch):
    async def slow(location):
        await asyncio.sleep(5)

    patch_m1(monkeypatch, "fetch_scenarios", slow)
    monkeypatch.setenv("M4_PROVIDER_TIMEOUT_SECONDS", "0.05")
    result = run(climate_provider.get_scenarios("pamplemousses-04"))
    assert result.status == "unavailable"
    assert result.error.startswith("TimeoutError")


def test_scenarios_invalid_payload_becomes_unavailable(monkeypatch):
    async def bad(location):
        return {"locationId": "pamplemousses-04"}  # missing required fields

    patch_m1(monkeypatch, "fetch_scenarios", bad)
    result = run(climate_provider.get_scenarios("pamplemousses-04"))
    assert result.status == "unavailable"
    assert "ValidationError" in result.error


def test_unknown_location_becomes_unavailable():
    result = run(climate_provider.get_scenarios("not-a-farm"))
    assert result.status == "unavailable"
    assert "Unknown M1 location" in result.error


def test_history_ok_from_real_payload(monkeypatch):
    async def fake(location, start, end):
        assert (start, end) == ("20210101", "20251231")
        return load_fixture(HISTORY)

    patch_m1(monkeypatch, "fetch_history", fake)
    result = run(climate_provider.get_history("pamplemousses-04"))
    assert result.status == "ok"
    assert result.called == "climateM1.services.history.fetch_history"


def test_history_network_failure_becomes_unavailable(monkeypatch):
    async def offline(location, start, end):
        raise ConnectionError("NASA POWER unreachable")

    patch_m1(monkeypatch, "fetch_history", offline)
    result = run(climate_provider.get_history("pamplemousses-04"))
    assert result.status == "unavailable"
    assert "ConnectionError" in result.error


def test_m1_import_failure_becomes_unavailable(monkeypatch):
    # Simulate M1's heavy deps (e.g. netCDF4) being broken at import time.
    monkeypatch.setitem(sys.modules, "climateM1.services.projections", None)
    result = run(climate_provider.get_scenarios("pamplemousses-04"))
    assert result.status == "unavailable"


@pytest.mark.skipif(os.getenv("M4_LIVE") != "1", reason="set M4_LIVE=1 for live M1 calls")
def test_live_m1_scenarios():
    result = run(climate_provider.get_scenarios("pamplemousses-04"))
    assert result.status in ("ok", "partial"), result.error


# ---------------------------------------------------------------------------
# M2 (pure functions — called for real)
# ---------------------------------------------------------------------------

def test_m2_rotation_real_call_matches_fixture():
    result = agriculture_provider.evaluate_rotation(["maize", "cowpea", "cabbage"])
    assert result.status == "ok"
    assert isinstance(result.data, M2RotationResult)
    assert result.data.model_dump(mode="json") == load_fixture(
        "m2_rotation__maize-cowpea-cabbage.json")


def test_m2_unknown_crop_becomes_unavailable():
    result = agriculture_provider.evaluate_rotation(["maize", "dragonfruit"])
    assert result.status == "unavailable"
    assert "Unknown crop: dragonfruit" in result.error


def test_m2_generate_real_call():
    result = agriculture_provider.generate_alternatives(["maize", "maize", "maize"], 3)
    assert result.status == "ok"
    assert result.data.alternatives_found == len(result.data.alternative_rotations)


def test_m2_suitability_insufficient_data_is_partial():
    result = agriculture_provider.check_suitability("cowpea")
    assert result.status == "partial"
    assert result.data.status == "insufficient_data"


def test_m2_water_is_not_implemented_and_has_no_values():
    result = agriculture_provider.get_water_demand(["maize"])
    assert result.status == "not_implemented"
    assert result.data is None


def test_m2_exception_inside_service_becomes_unavailable(monkeypatch):
    import agricultureM2.rotation_engine as engine

    def boom(crop_ids):
        raise FileNotFoundError("Verified crop catalog not found.")

    monkeypatch.setattr(engine, "evaluate_rotation", boom)
    result = agriculture_provider.evaluate_rotation(["maize", "cowpea"])
    assert result.status == "unavailable"
    assert "FileNotFoundError" in result.error


# ---------------------------------------------------------------------------
# M3 / M5 (not implemented yet — must degrade, and pick up the contract later)
# ---------------------------------------------------------------------------

def test_m3_not_implemented_yet():
    result = farm_provider.get_farm_context("farm-1")
    assert result.status == "not_implemented"
    assert result.data is None


def test_m5_not_implemented_yet():
    result = resilience_provider.get_resilience("pamplemousses-04", "ssp370", 2050, ["maize"])
    assert result.status == "not_implemented"
    assert result.data is None


def test_m3_contract_is_used_once_published(monkeypatch):
    fake = types.ModuleType("mappingM3.farm_profile")
    fake.get_farm_profile = lambda farm_id: {
        "farm_id": farm_id, "location_id": "flacq-02", "source": "M3"}
    monkeypatch.setitem(sys.modules, "mappingM3.farm_profile", fake)
    import mappingM3
    monkeypatch.setattr(mappingM3, "farm_profile", fake, raising=False)

    result = farm_provider.get_farm_context("farm-7")
    assert result.status == "ok"
    assert result.data.soil_ph is None  # not supplied -> stays None


def test_m5_contract_failure_becomes_unavailable(monkeypatch):
    fake = types.ModuleType("resilienceM5.stress_test")

    def broken(*args):
        raise ValueError("stress test failed")

    fake.run_stress_test = broken
    monkeypatch.setitem(sys.modules, "resilienceM5.stress_test", fake)
    import resilienceM5
    monkeypatch.setattr(resilienceM5, "stress_test", fake, raising=False)

    result = resilience_provider.get_resilience("pamplemousses-04", "ssp370", 2050, ["maize"])
    assert result.status == "unavailable"
    assert "stress test failed" in result.error
