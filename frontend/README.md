# CropCompass — Frontend (M3)

Mobile-first web app (React + TypeScript + Vite) in the CropCompass design.
Every number comes from the FastAPI backend (M1–M5). If the backend cannot be
reached, the app shows real data captured earlier from the same backend and labels it **Cached**.
Nothing is invented: values the backend does not compute yet (plan scores, crop water need)
are shown as "not calculated yet".

## Run

```bash
# 1. backend (from backend/)
uvicorn app:app --reload            # http://127.0.0.1:8000

# 2. frontend (from frontend/)
npm install
npm run dev                         # http://localhost:5173  (open on a phone: use the Network URL)
```

`/api/*` calls are proxied to the backend (`VITE_BACKEND_URL`, default `http://127.0.0.1:8000`, see `.env.example`).
Production build: `npm run build && npm run preview`.

## Screens → endpoints

| Screen | Uses |
|---|---|
| Home | `GET /api/farms`, `GET /api/farms/{id}`, `GET /api/climate/history` |
| Fields, field sheet, Add field | `GET/POST/PATCH /api/farms…`, `GET /api/farms/locations`, `GET /api/agriculture/crops` |
| Plans | `POST /api/agriculture/generate`, `GET /api/agriculture/suitability/{crop}` |
| Water | `PATCH /api/farms/{id}` (water slider, saved), `GET /api/climate/history` (seasonal rain) |
| Future | `GET /api/climate/scenarios`, `POST /api/resilience/climate-twin`, `POST /api/resilience/stress-test` |
| Evidence passport | `POST /api/intelligence/analyze` |
| Ask | `POST /api/intelligence/assistant` |

Cached fallbacks live in `src/fallback/` (captured from the backend on 15 Nov 2026; climate data for Pamplemousses-04).
