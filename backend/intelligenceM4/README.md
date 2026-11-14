# intelligenceM4: Explainable AI, Evidence Passport & Integration

M4 makes CropCompass results traceable. It explains what M1 (climate), M2 (agriculture), M3 (farm/mapping) and M5 (resilience) computed, shows where each fact came from, and lists what is missing. It does not compute agronomic results of its own.

See [API_CONTRACT.md](API_CONTRACT.md) for endpoints, integrity rules and upstream contracts.

## Layout

```
intelligenceM4/
├── schemas.py              # all M4 contracts (Phase 1)
├── routes.py               # /api/intelligence router
├── evidence_passport.py    # Phase 2
├── blind_spot_detector.py  # Phase 3
├── assistant.py            # Phase 4 (template-first, LLM optional)
├── orchestrator.py         # Phase 5
├── providers/              # thin in-process adapters, never raise
│   ├── __init__.py         # safe_call / safe_call_async / not_implemented
│   ├── climate_provider.py # M1 service layer
│   ├── agriculture_provider.py  # M2 service layer
│   ├── farm_provider.py    # M3 (proposed contract)
│   └── resilience_provider.py   # M5 (proposed contract)
├── rag/                    # reserved; MVP grounds in structured JSON
├── fixtures/               # REAL M1/M2 outputs + manifest.json
├── data_quality.py         # scaffold placeholder (unused)
└── rag_assistant.py        # scaffold placeholder (unused)
```

## Principles

1. **Consume, don't duplicate.** Providers call other modules' service functions and validate the results. They contain no copied logic.
2. **Missing data is a blind spot, never a default.**
3. **Every upstream value is traceable** through `provenance.field_path`, and claims carry no numbers.
4. **Failure-tolerant.** A failing module yields `unavailable` / `not_implemented` without crashing the analysis.

## Tests

```bash
cd backend
python -m pytest tests/test_m4_*.py -v
```
