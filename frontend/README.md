# CropCompass — Frontend (M3)

Mobile-first web app (React + TypeScript + Vite) in the CropCompass design.
Every number comes from the FastAPI backend (M1–M5). If the backend cannot be
reached, the app shows real data captured earlier from the same backend and labels it **Cached**.
Nothing is invented: values the backend does not compute yet (plan scores, crop water need)
are shown as "not calculated yet".

## Run

```bash
# From frontend/ (uses the hosted Render backend)
npm install
npm run dev                         # http://localhost:5173  (open on a phone: use the Network URL)
```

`/api/*` calls are proxied to `https://cropcompass-api-i27c.onrender.com` in both development and preview. No local backend is required. Set `VITE_API_URL` to use another hosted backend, or `VITE_BACKEND_URL` to override it (for example, `http://127.0.0.1:8000` for local backend development). Restart Vite after changing environment settings. See `.env.example`.
On Vercel, `vercel.json` forwards `/api/*` to Render before the SPA fallback. Other static hosts need an equivalent API proxy.
Production preview: `npm run preview` (builds first, then serves at `http://localhost:4173`).
Home, Fields, Plans, Water, and Future are in-app tabs served from `/`.

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
