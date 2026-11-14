"""Phase 4 — Grounded assistant and POST /api/intelligence/assistant.

All analyses are built from REAL M1/M2 fixtures. No test can reach a real LLM:
an autouse fixture removes ANTHROPIC_API_KEY and blocks `import anthropic`;
LLM tests replace assistant._call_llm with a mock.
"""

import os
import re
import sys
import types

import pytest
from fastapi.testclient import TestClient

from app import app
from intelligenceM4 import assistant
from intelligenceM4.assistant import LLMUnavailable, check_answer, classify
from intelligenceM4.evidence_passport import build_passport
from intelligenceM4.fixtures import load_fixture
from intelligenceM4.schemas import AnalysisBundle, AssistantRequest, strip_allowed_tokens

client = TestClient(app)


LLM_ENV = ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "M4_LLM_PROVIDER",
           "M4_LLM_MODEL", "M4_LLM_TIMEOUT_SECONDS")
SDK_MODULES = ("anthropic", "google.genai", "google.genai.types", "google.genai.errors")


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch, tmp_path):
    for name in LLM_ENV:
        monkeypatch.delenv(name, raising=False)
    for module in SDK_MODULES:  # importing any real SDK -> ImportError
        monkeypatch.setitem(sys.modules, module, None)
    # Never read a developer's real backend/.env during tests.
    monkeypatch.setattr(assistant, "DOTENV_PATH", tmp_path / "no.env")


def bundle_json(**overrides):
    data = {
        "analysis_id": "test-assistant",
        "farm": {"location_id": "pamplemousses-04"},
        "selected_scenario": "ssp370",
        "selected_year": 2050,
        "climate": {"scenarios": load_fixture("m1_scenarios__pamplemousses-04.json"),
                    "history": load_fixture("m1_history__pamplemousses-04.json")},
        "agriculture": {
            "rotation": load_fixture("m2_rotation__maize-cowpea-cabbage.json"),
            "alternatives": load_fixture("m2_generate__maize-cowpea-cabbage__max3.json"),
            "suitability": [load_fixture("m2_suitability__cowpea__no-inputs.json")],
        },
    }
    data.update(overrides)
    return data


def ask(question, use_llm=False, **overrides):
    return assistant.answer(AssistantRequest(
        question=question, analysis=bundle_json(**overrides), use_llm=use_llm))


def passport(**overrides):
    return build_passport(AnalysisBundle.model_validate(bundle_json(**overrides)))


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("question,intent", [
    ("Why cowpea?", "why_crop"),
    ("Why should I consider cowpea in my crop rotation?", "why_crop"),
    ("Why is Rotation B preferable under the 2050 scenario?", "compare_rotations"),
    ("Which rotation is better?", "compare_rotations"),
    ("What will the climate be like in 2050?", "climate_outlook"),
    ("How hot will it get?", "climate_outlook"),
    ("Tell me a joke", "refuse:not_about_this_analysis"),
    ("Is there enough water for this rotation?", "water"),
    ("What data is missing?", "missing_data"),
    ("What's missing?", "missing_data"),
    ("How sure is this?", "confidence"),
    ("How much will my yield increase?", "refuse:yield_prediction"),
])
def test_classify(question, intent):
    assert classify(question, AnalysisBundle.model_validate(bundle_json()))[0] == intent


# ---------------------------------------------------------------------------
# Intents on real data
# ---------------------------------------------------------------------------

def test_why_cowpea_matches_the_plan_example():
    r = ask("Why cowpea?")
    text = r.answer.lower()
    assert (r.mode, r.intent) == ("template", "why_crop")
    assert "legume" in text and "fabaceae" in text
    assert "nitrogen-fixing" in text and "m2's crop catalog" in text
    assert "has not established that cowpea is suitable" in text
    assert "does not quantify a nitrogen benefit" in text
    # Exactly one suitability statement: the specific M2 one.
    assert text.count("suitable") == 1
    assert "does not establish that the crop is suitable" not in text
    assert r.answer.endswith("Still open for this crop: suitability inputs not passed, "
                             "soil pH missing, and water demand not calculated.")
    assert "[" not in r.answer
    assert {"ev-family-cowpea", "ev-nfix-cowpea", "ev-suit-cowpea"} <= set(r.cited_evidence)
    assert {"SUITABILITY_INPUT_NOT_PASSED", "SOIL_PH_MISSING",
            "WATER_DEMAND_NOT_IMPLEMENTED"} <= set(r.blind_spots)
    assert not re.search(r"\d", strip_allowed_tokens(r.answer))  # only ids like M2


def test_every_blind_spot_code_has_a_plain_label():
    from intelligenceM4.blind_spot_detector import TEMPLATES
    assert set(TEMPLATES) <= set(assistant.BLIND_SPOT_LABELS)
    for label in assistant.BLIND_SPOT_LABELS.values():
        assert not re.search(r"\d", strip_allowed_tokens(label))


def test_why_maize_is_not_called_nitrogen_fixing():
    r = ask("Why maize?")
    assert "does not mark it as nitrogen-fixing" in r.answer
    assert "ev-nfix-maize" not in r.cited_evidence


def test_why_crop_only_in_an_alternative():
    r = ask("Why tomato?")
    assert r.intent == "why_crop"
    assert "not in your current rotation" in r.answer
    assert "alternative rotation A, B, C" in r.answer
    assert "ev-alt-ranking" in r.cited_evidence


def test_compare_never_says_a_rotation_is_better():
    r = ask("Why is Rotation B preferable under 2050?")
    assert r.intent == "compare_rotations"
    assert "CropCompass has not ranked these rotations" in r.answer
    assert "cannot say that Rotation B is preferable" in r.answer
    assert '"not_calibrated"' in r.answer and '"not_evaluated"' in r.answer
    assert "Rotation B (maize → tomato → onion)" in r.answer
    assert "Your current rotation (maize → cowpea → cabbage)" in r.answer
    assert "nitrogen-fixing crops: cowpea" in r.answer
    assert not re.search(r"(?<!say that )Rotation [A-Z] is (?:better|preferable)", r.answer)
    assert not re.search(r"\b(?:recommend(?:ed)?|best|should switch)\b", r.answer, re.I)
    assert {"ev-alt-ranking", "ev-alt-feasibility", "ev-alt-B-rotation",
            "ev-alt-B-nfix", "ev-alt-B-repeat"} <= set(r.cited_evidence)
    assert "Rotation A" not in r.answer and "Rotation C" not in r.answer
    assert "M5_NOT_IMPLEMENTED" in r.blind_spots


def test_compare_without_letter_lists_every_alternative():
    r = ask("Which rotation is better?")
    for label in "ABC":
        assert f"Rotation {label} (" in r.answer


def test_compare_unknown_rotation_letter():
    r = ask("Is rotation Z better?")
    assert "There is no Rotation Z in this analysis" in r.answer


def test_compare_without_alternatives():
    r = ask("Which rotation is better?", agriculture={
        "rotation": load_fixture("m2_rotation__maize-cowpea-cabbage.json")})
    assert "has not supplied alternative rotations" in r.answer


def test_climate_outlook_copies_m1_values():
    r = ask("What is the climate outlook for 2050?")
    scen = load_fixture("m1_scenarios__pamplemousses-04.json")
    point = next(v for e in scen["ensemble"] if e["id"] == "ssp370"
                 for v in e["values"] if v["year"] == 2050)
    assert r.intent == "climate_outlook"
    assert f"{point['rainfallMm']['mean']} mm/year" in r.answer
    assert f"{point['temperatureC']['spread']} °C" in r.answer
    assert "not a probability range" in r.answer
    assert "not a forecast for your field" in r.answer
    assert {"ev-proj-rain-mean", "ev-proj-temp-spread"} <= set(r.cited_evidence)
    assert "CLIMATE_RESOLUTION" in r.blind_spots


def test_water_answer_reports_missing_demand_and_budget():
    r = ask("Is there enough water?")
    assert r.intent == "water"
    assert "cannot yet say whether this rotation fits your water supply" in r.answer
    assert {"WATER_DEMAND_NOT_IMPLEMENTED", "IRRIGATION_BUDGET_MISSING"} <= set(r.blind_spots)


def test_water_answer_cites_supplied_budget():
    r = ask("Is there enough water?",
            farm={"location_id": "pamplemousses-04", "irrigation_budget_m3": 12000})
    assert "12000.0 cubic metres" in r.answer
    assert "ev-farm-irrigation-budget" in r.cited_evidence


def test_missing_data_lists_every_blind_spot():
    r = ask("What data is missing?")
    p = passport()
    assert r.intent == "missing_data"
    assert r.blind_spots == [s.code for s in p.blind_spots]
    assert "Provide the soil pH from a recent soil test" in r.answer


def test_confidence_reports_recommendation_status():
    r = ask("How sure is this?")
    assert r.intent == "confidence"
    assert r.answer.startswith("Overall status: requires further validation.")
    assert "ev-soil-score" in r.cited_evidence


def test_insufficient_evidence_confidence():
    r = ask("How sure is this?", climate={})
    assert r.answer.startswith("Overall status: insufficient evidence.")


@pytest.mark.parametrize("question", [
    "Why cowpea?", "Why is Rotation B preferable under 2050?", "What data is missing?",
    "How sure is this?", "What is the climate outlook?", "Is there enough water?",
])
def test_every_in_scope_answer_passes_the_guard(question):
    r = ask(question)
    assert r.mode == "template", r.refusal_reason
    assert check_answer(r.answer, r.cited_evidence, r.blind_spots, passport()) == []


# ---------------------------------------------------------------------------
# Out of scope
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("question,reason", [
    ("How much will my yield increase?", "yield_prediction"),
    ("Will this rotation make a profit?", "financial_outcome"),
    ("How much income will cowpea bring?", "financial_outcome"),
    ("How much fertiliser should I apply?", "input_dosage"),
    ("What pesticide dose for cabbage?", "input_dosage"),
    ("By what % will my soil improve with cowpea?", "quantified_soil_improvement"),
    ("What should I plant next season?", "crop_choice"),
    ("What is the capital of France?", "not_about_this_analysis"),
    ("Why rice?", "not_about_this_analysis"),
])
def test_out_of_scope_questions_are_refused(question, reason):
    r = ask(question)
    assert r.mode == "refused"
    assert r.refusal_reason == reason
    assert r.cited_evidence == [] and r.blind_spots == []
    assert "You could ask instead" in r.answer and "“Why cowpea?”" in r.answer
    assert check_answer(r.answer, [], [], passport()) == []


# ---------------------------------------------------------------------------
# Answer guard
# ---------------------------------------------------------------------------

def test_guard_rejects_invented_number():
    p = passport()
    problems = check_answer("Cowpea fixes 120 kg of nitrogen per hectare.",
                            ["ev-nfix-cowpea"], [], p)
    assert problems == ["number 120 is not in the cited evidence"]


def test_guard_rejects_number_from_uncited_evidence():
    p = passport()
    mean = next(e for e in p.evidence if e.id == "ev-proj-rain-mean").value
    assert check_answer(f"Rainfall {mean} mm/year.", ["ev-proj-rain-mean"], [], p) == []
    assert check_answer(f"Rainfall {mean} mm/year.", ["ev-proj"], [], p)


@pytest.mark.parametrize("text", [
    "Cowpea will increase your yield.",
    "This rotation will greatly improve your soil.",
    "We guarantee results.",
    "Expect a 20% improvement.",
    "This brings higher yields.",
    "Good for profit.",
])
def test_guard_rejects_outcome_promises(text):
    assert any(v.startswith("outcome promise") for v in check_answer(text, [], [], passport()))


def test_guard_rejects_unknown_ids_and_codes():
    problems = check_answer("Fine.", ["ev-made-up"], ["NOT_A_CODE"], passport())
    assert len(problems) == 2


def test_guard_allows_registry_identifiers_and_cited_blind_spot_values():
    p = passport()
    assert check_answer("Projections for 2050 under SSP3-7.0 from M1 and M2.", [], [], p) == []
    grid = "0.25° × 0.25° (~25 km)"
    assert check_answer(f"Grid {grid}.", [], ["CLIMATE_RESOLUTION"], p) == []
    assert check_answer(f"Grid {grid}.", [], [], p)


# ---------------------------------------------------------------------------
# Optional LLM (always mocked)
# ---------------------------------------------------------------------------

def use_mock_llm(monkeypatch, reply):
    calls = []

    def fake(settings, system, user_content):
        calls.append((settings, system, user_content))
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.setattr(assistant, "_call_llm", fake)
    return calls


def test_works_with_no_llm_configured():
    r = ask("Why cowpea?", use_llm=True)
    assert r.mode == "template"
    assert r.fallback_reason == "LLM unavailable: ANTHROPIC_API_KEY is not set"
    assert "legume" in r.answer


def test_llm_package_missing_falls_back(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    r = ask("Why cowpea?", use_llm=True)
    assert r.mode == "template"
    assert r.fallback_reason == "LLM unavailable: the anthropic package is not installed"


def test_unsupported_provider_falls_back(monkeypatch):
    monkeypatch.setenv("M4_LLM_PROVIDER", "someother")
    r = ask("Why cowpea?", use_llm=True)
    assert "unsupported M4_LLM_PROVIDER" in r.fallback_reason


def test_llm_rephrasing_accepted_when_grounded(monkeypatch):
    calls = use_mock_llm(monkeypatch, "Cowpea is a legume that M2's catalog lists as "
                                      "nitrogen-fixing. Its benefit is not quantified and its "
                                      "suitability for your field is not established.")
    r = ask("Why cowpea?", use_llm=True)
    assert r.mode == "llm" and r.fallback_reason is None
    assert r.answer.startswith("Cowpea is a legume")
    _, system, user_content = calls[0]
    assert "Use only the facts" in system
    assert '"ev-nfix-cowpea"' in user_content          # cited evidence is sent
    assert '"ev-proj-rain-mean"' not in user_content   # uncited evidence is not


def test_llm_invented_number_falls_back_to_template(monkeypatch):
    use_mock_llm(monkeypatch, "Cowpea adds 120 kg of nitrogen per hectare.")
    r = ask("Why cowpea?", use_llm=True)
    assert r.mode == "template"
    assert "number 120" in r.fallback_reason
    assert "120" not in r.answer and "legume" in r.answer


def test_llm_yield_promise_falls_back_to_template(monkeypatch):
    use_mock_llm(monkeypatch, "Planting cowpea will increase your yield next season.")
    r = ask("Why cowpea?", use_llm=True)
    assert r.mode == "template"
    assert "outcome promise" in r.fallback_reason
    assert "increase your yield" not in r.answer


@pytest.mark.parametrize("error,expected", [
    (LLMUnavailable("LLM request timed out after 20s"), "timed out"),
    (RuntimeError("boom"), "RuntimeError"),
])
def test_llm_errors_fall_back_to_template(monkeypatch, error, expected):
    use_mock_llm(monkeypatch, error)
    r = ask("Why cowpea?", use_llm=True)
    assert r.mode == "template" and expected in r.fallback_reason


def test_refused_questions_never_call_the_llm(monkeypatch):
    calls = use_mock_llm(monkeypatch, "anything")
    r = ask("How much will my yield increase?", use_llm=True)
    assert r.mode == "refused" and calls == []


# ---------------------------------------------------------------------------
# Provider settings: defaults, .env
# ---------------------------------------------------------------------------

def test_default_models(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert assistant.llm_settings()["model"] == "claude-haiku-5-5"
    monkeypatch.setenv("M4_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert assistant.llm_settings()["model"] == "gemini-3.8-flash"
    monkeypatch.setenv("M4_LLM_MODEL", "gemini-custom")
    assert assistant.llm_settings()["model"] == "gemini-custom"


def test_settings_read_from_dotenv_file_and_env_wins(monkeypatch, tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("M4_LLM_PROVIDER=gemini\nGEMINI_API_KEY=from-dotenv\n", encoding="utf-8")
    monkeypatch.setattr(assistant, "DOTENV_PATH", dotenv)
    settings = assistant.llm_settings()
    assert (settings["provider"], settings["api_key"]) == ("gemini", "from-dotenv")
    assert "GEMINI_API_KEY" not in os.environ  # the file is read, never exported
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    assert assistant.llm_settings()["api_key"] == "from-env"


# ---------------------------------------------------------------------------
# Real provider code paths, against fake SDK modules (no network)
# ---------------------------------------------------------------------------

class _Text:
    type = "text"

    def __init__(self, text):
        self.text = text


def fake_anthropic(monkeypatch, reply="Cowpea is a legume.", raise_exc=None):
    """Minimal stand-in for the anthropic package; records the call."""
    mod = types.ModuleType("anthropic")
    calls = {}

    class APIError(Exception):
        pass

    class APIStatusError(APIError):
        status_code = 500

    class RateLimitError(APIStatusError):
        pass

    class AuthenticationError(APIStatusError):
        pass

    class APIConnectionError(APIError):
        pass

    class APITimeoutError(APIConnectionError):
        pass

    class Messages:
        def create(self, **kwargs):
            calls["create"] = kwargs
            if raise_exc is not None:
                raise getattr(mod, raise_exc)("fail")
            return types.SimpleNamespace(stop_reason="end_turn", content=[_Text(reply)])

    class Anthropic:
        def __init__(self, **kwargs):
            calls["client"] = kwargs
            self.messages = Messages()

    for cls in (APIStatusError, RateLimitError, AuthenticationError,
                APIConnectionError, APITimeoutError, Anthropic):
        setattr(mod, cls.__name__, cls)
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    return calls


def fake_genai(monkeypatch, reply="Cowpea is a legume.", raise_exc=None, finish="STOP"):
    """Minimal stand-in for google-genai; records the call."""
    genai = types.ModuleType("google.genai")
    gtypes = types.ModuleType("google.genai.types")
    errors = types.ModuleType("google.genai.errors")
    calls = {}

    class APIError(Exception):
        code = 429

    gtypes.HttpOptions = lambda **kw: ("HttpOptions", kw)
    gtypes.HttpRetryOptions = lambda **kw: ("HttpRetryOptions", kw)
    gtypes.GenerateContentConfig = lambda **kw: ("GenerateContentConfig", kw)
    errors.APIError = APIError

    class Models:
        def generate_content(self, **kwargs):
            calls["generate_content"] = kwargs
            if raise_exc == "APIError":
                raise APIError("quota exceeded")
            if raise_exc is not None:
                raise raise_exc
            candidate = types.SimpleNamespace(finish_reason=types.SimpleNamespace(name=finish))
            return types.SimpleNamespace(text=reply, candidates=[candidate])

    class Client:
        def __init__(self, **kwargs):
            calls["client"] = kwargs
            self.models = Models()

    genai.Client = Client
    for name, mod in (("google.genai", genai), ("google.genai.types", gtypes),
                      ("google.genai.errors", errors)):
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setenv("M4_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    return calls


def test_anthropic_call_is_minimal(monkeypatch):
    calls = fake_anthropic(monkeypatch)
    r = ask("Why cowpea?", use_llm=True)
    assert r.mode == "llm" and r.answer == "Cowpea is a legume."
    assert set(calls["create"]) == {"model", "max_tokens", "system", "messages"}
    assert calls["create"]["model"] == "claude-haiku-5-5"
    assert calls["client"] == {"api_key": "test-key-not-real", "timeout": 20.0,
                               "max_retries": 0}


def test_anthropic_timeout_falls_back(monkeypatch):
    fake_anthropic(monkeypatch, raise_exc="APITimeoutError")
    r = ask("Why cowpea?", use_llm=True)
    assert r.mode == "template" and "timed out after 20s" in r.fallback_reason


def test_gemini_call_is_minimal(monkeypatch):
    calls = fake_genai(monkeypatch)
    r = ask("Why cowpea?", use_llm=True)
    assert r.mode == "llm" and r.answer == "Cowpea is a legume."
    call = calls["generate_content"]
    assert set(call) == {"model", "contents", "config"}
    assert call["model"] == "gemini-3.8-flash"
    assert call["config"] == ("GenerateContentConfig", {
        "system_instruction": assistant.LLM_SYSTEM_PROMPT,
        "max_output_tokens": assistant.MAX_OUTPUT_TOKENS})
    assert calls["client"] == {"api_key": "test-key-not-real", "http_options": (
        "HttpOptions", {"timeout": 20000,
                        "retry_options": ("HttpRetryOptions", {"attempts": 1})})}


def test_gemini_no_retry_options_are_valid_for_installed_sdk(monkeypatch):
    """The real google-genai types accept the options we pass (no network call)."""
    for module in ("google.genai", "google.genai.types", "google.genai.errors"):
        monkeypatch.delitem(sys.modules, module)  # undo the autouse block for this test
    gtypes = pytest.importorskip("google.genai.types")
    options = gtypes.HttpOptions(timeout=20000,
                                 retry_options=gtypes.HttpRetryOptions(attempts=1))
    assert options.timeout == 20000 and options.retry_options.attempts == 1


def test_gemini_invented_number_falls_back(monkeypatch):
    fake_genai(monkeypatch, reply="Cowpea adds 120 kg of nitrogen per hectare.")
    r = ask("Why cowpea?", use_llm=True)
    assert r.mode == "template" and "number 120" in r.fallback_reason
    assert "120" not in r.answer


def test_gemini_yield_promise_falls_back(monkeypatch):
    fake_genai(monkeypatch, reply="Cowpea will increase your yield.")
    r = ask("Why cowpea?", use_llm=True)
    assert r.mode == "template" and "outcome promise" in r.fallback_reason


def test_gemini_missing_key_falls_back(monkeypatch):
    monkeypatch.setenv("M4_LLM_PROVIDER", "gemini")
    r = ask("Why cowpea?", use_llm=True)
    assert r.fallback_reason == "LLM unavailable: GEMINI_API_KEY is not set"


def test_gemini_missing_package_falls_back(monkeypatch):
    monkeypatch.setenv("M4_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    r = ask("Why cowpea?", use_llm=True)
    assert r.fallback_reason == "LLM unavailable: the google-genai package is not installed"


def test_gemini_timeout_falls_back(monkeypatch):
    import httpx
    fake_genai(monkeypatch, raise_exc=httpx.ReadTimeout("timed out"))
    r = ask("Why cowpea?", use_llm=True)
    assert r.mode == "template" and "timed out after 20s" in r.fallback_reason


def test_gemini_api_error_falls_back(monkeypatch):
    fake_genai(monkeypatch, raise_exc="APIError")
    r = ask("Why cowpea?", use_llm=True)
    assert r.mode == "template"
    assert r.fallback_reason == "LLM unavailable: LLM API error (429)"


def test_gemini_safety_block_falls_back(monkeypatch):
    fake_genai(monkeypatch, finish="SAFETY")
    r = ask("Why cowpea?", use_llm=True)
    assert r.mode == "template" and "declined" in r.fallback_reason


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

def test_assistant_endpoint():
    response = client.post("/api/intelligence/assistant",
                           json={"question": "Why cowpea?", "analysis": bundle_json()})
    assert response.status_code == 200, response.text
    assert response.json()["intent"] == "why_crop"


def test_assistant_endpoint_validates_question():
    response = client.post("/api/intelligence/assistant",
                           json={"question": "hi", "analysis": bundle_json()})
    assert response.status_code == 422


def test_assistant_endpoint_is_in_swagger():
    assert "/api/intelligence/assistant" in client.get("/openapi.json").json()["paths"]


def test_saved_assistant_examples_match_current_output():
    requests = load_fixture("example_assistant_request.json")
    saved = load_fixture("example_assistant_response.json")
    assert len(requests) == len(saved) == 3
    fresh = [client.post("/api/intelligence/assistant", json=body).json() for body in requests]
    assert fresh == saved, "Regenerate: python -m intelligenceM4.fixtures.build_fixtures --example-only"
