# Integration Test Results

## End-to-end workflows validated locally

### Startup and routing
The unified FastAPI app starts successfully and registers routers for the major backend modules.

Observed validation:
- `uvicorn app:app --host 127.0.0.1 --port 8000` started successfully
- `/health` returned `200` with `{"status":"healthy"}`
- `/openapi.json` returned `200`
- Generated OpenAPI indicated 16 service paths

### Module registration
The unified app includes climate, agriculture, intelligence, and resilience routers without import-time failures.

### Deterministic backend suite
The full backend test run passed:

```text
269 passed, 2 skipped, 1 warning in 19.12s
```

This includes M1 climate logic, M2 agriculture evaluation, M4 explainability and provenance checks, and M5 resilience logic.

## Cross-module integration evidence
The integration tests exercise the cross-module flows defined by the repo and validate contract-level behavior. The backend did not display duplicate route registration or import errors in the local run.

## Unverified external path
The following integration steps were not live-validated in this session because the environment did not perform live external NASA/FAO requests:

- live NASA POWER historical fetches
- live NEX-GDDP-CMIP6 projection fetches
- remote FAO/GAEZ lookups

These behaviors are represented in the code and tests, but the system-level external-data path remains a network-dependent validation step rather than a confirmed local execution.

## Final status
The backend is operational and the locally deterministic integration path is successful. External data-source validation remains a remaining environment-dependent task.
