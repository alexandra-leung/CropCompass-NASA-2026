# Backend Test Results

## Commands executed

### Full backend test run
```bash
cd backend
python -m pytest -q tests
```

### Runtime smoke validation
```bash
cd backend
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

### OpenAPI / health checks
```bash
python -c "import requests; r=requests.get('http://127.0.0.1:8000/health', timeout=15); print(r.status_code); print(r.json())"
python -c "import requests; r=requests.get('http://127.0.0.1:8000/openapi.json', timeout=15); print(r.status_code); data=r.json(); print(len(data.get('paths', {})))"
```

## Actual results

### Pytest summary
```text
269 passed, 2 skipped, 1 warning in 19.12s
```

### Runtime summary
```text
Uvicorn running on http://127.0.0.1:8000
```

```text
HTTP 200 from /health -> {'status': 'healthy'}
HTTP 200 from /openapi.json -> OpenAPI document served successfully
```

## Coverage
Coverage was not measured in this session because the project did not run a coverage tool in the local validation step. The command `python -m pytest --cov=. --cov-report=term-missing` was not executed here.

## Test classification
- Unit tests: included in `backend/tests/`
- Integration tests: included in `backend/tests/`
- External-service tests: present but separated by environment gating (`M4_LIVE`, NASA-dependent fixtures, and network-dependent logic)
- Scientific validation tests: included in the resilience and climate modules
- Backend API smoke tests: completed via FastAPI startup and HTTP checks

## Outcome
The deterministic local backend test suite passed without failures. The only non-passing status was the expected skip count for tests intentionally gated or not run in this local environment.
