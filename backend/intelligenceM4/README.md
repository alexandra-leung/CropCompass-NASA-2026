# intelligenceM4: Explainable AI, Evidence Passport & Integration

M4 makes CropCompass trustworthy and integrated. One call (`/analyze`) gathers the results of M1 (climate), M2 (agriculture), M3 (farm) and M5 (resilience) into a single analysis. It shows where every fact came from, lists what data is missing and who can supply it, and answers farmer questions using only that evidence.

M4 **computes nothing agronomic**. It does not rank rotations, predict yields, calculate water use or invent defaults. Missing data becomes a *blind spot*, never a value.

Full field-level reference: [API_CONTRACT.md](API_CONTRACT.md).

## What it provides

| Endpoint (`POST /api/intelligence/...`) | What it does |
|---|---|
| `/analyze` | Calls M1, M2 and, when available, M3/M5, then returns the bundle, Evidence Passport, blind spots and module statuses. A failing or slow module never fails the request. |
| `/evidence` | **Evidence Passport.** Every claim comes with the upstream value it rests on, the exact `field_path` it was copied from, the rule applied, and verbatim upstream limitations. Values are re-checked against the bundle before the response is returned. |
| `/blind-spots` | Deterministic rules for missing or incomplete data. Each one says what is missing, what the farmer can do and which module must act. |
| `/assistant` | Answers "Why cowpea?", "Why is Rotation B preferable?", "What data is missing?", "How sure is this?", climate and water questions from the evidence only. Refuses yield, money, dosing and "what should I plant" questions. |

## Run it

```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app:app --reload --port 8000
```

Then open **http://127.0.0.1:8000/docs** (Swagger).

**M1 cache:** `/analyze` uses M1's SQLite cache of NASA NEX-GDDP-CMIP6 data. If the cache is older than M1's 6-hour TTL, M1 re-downloads from NASA, which takes minutes and rewrites `backend/data/climate_cache.sqlite3`. M1 history is always a live NASA POWER call; if it fails or times out, the analysis continues and reports a blind spot.

## Tests

```bash
cd backend
python -m pytest tests/test_m4_*.py -v
```

The tests run offline: no NASA calls and no LLM calls. `M4_LIVE=1` adds one live M1 call. To regenerate the frontend examples, run `python -m intelligenceM4.fixtures.build_fixtures --example-only`.

## Optional LLM rephrasing

The assistant works with **no LLM**. With `"use_llm": true`, an LLM may rephrase the template answer, given only the cited evidence. The answer guard then re-checks the LLM's text, and any problem returns the template answer with a `fallback_reason`.

Keys come from the environment or `backend/.env` only. `.env` is gitignored; never commit keys.

```ini
# backend/.env  (pick one provider)
M4_LLM_PROVIDER=gemini
GEMINI_API_KEY=your-key-here
# or
M4_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your-key-here
```

Install the matching package, since neither is in `requirements.txt`: `pip install google-genai` or `pip install anthropic`.

| Provider | Default model | Override |
|---|---|---|
| `gemini` | `gemini-3.8-flash` | `M4_LLM_MODEL` |
| `anthropic` | `claude-haiku-5-5` | `M4_LLM_MODEL` |

Timeout: `M4_LLM_TIMEOUT_SECONDS` (default 20, no retries).

## Demo script (Swagger, in order)

Ready-made bodies are in `fixtures/`.

1. **Full analysis.** Send `POST /api/intelligence/analyze` with the body from `fixtures/example_analyze_request.json` (Pamplemousses-04, maize → cowpea → cabbage, SSP3-7.0, 2050). Point out:
   - `modules`: M1 ok, M2 partial, M3/M5 not implemented yet.
   - `bundle.agriculture.suitability_inputs`: M1's projected 2050 temperature was passed to M2, with its `field_path`.
   - `passport.recommendation_status` is `requires_further_validation`.
   - `blind_spot_report`: M2's catalog has no temperature ranges, soil pH is missing, and so on.
2. **"Why this recommendation?"** Copy `bundle` from step 1 and send `POST /api/intelligence/assistant` with `{"question": "Why cowpea?", "analysis": <bundle>}`. The answer cites the legume and nitrogen-fixing evidence from M2's catalog, and says the benefit is not quantified and suitability is not established.
3. In the same way, ask **"Why is Rotation B preferable under 2050?"**. CropCompass says plainly that it has not ranked the rotations, then lists the facts M2 reports.
4. Ask **"What data is missing?"**: every gap, what the farmer can do, and which team must act.
5. Ask **"How much will my yield increase?"**. It is refused, with suggested questions it can answer.
6. *(Optional)* Re-run step 1 with `"soil_ph": 6.5` in `farm`. `SOIL_PH_MISSING` disappears, and M2 now reports that its catalog lacks pH ranges too.

The bundle is large to paste. `fixtures/example_assistant_request.json` holds three ready-to-send `/assistant` bodies.

## Layout

```
intelligenceM4/
├── routes.py               # the four endpoints
├── schemas.py              # all contracts
├── orchestrator.py         # /analyze
├── evidence_passport.py    # /evidence
├── blind_spot_detector.py  # /blind-spots
├── assistant.py            # /assistant (+ optional Anthropic / Gemini rephrasing)
├── traceability.py         # field_path resolution and checks
├── providers/              # thin in-process adapters to M1/M2/M3/M5; never raise
├── fixtures/               # real M1/M2 outputs + frontend examples (manifest.json)
├── rag/                    # reserved; answers are grounded in structured JSON
├── data_quality.py         # scaffold placeholder (unused)
└── rag_assistant.py        # scaffold placeholder (unused)
```
