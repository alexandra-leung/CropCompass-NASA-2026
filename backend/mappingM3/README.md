# M3 — Farm Mapping & Farmer Inputs

Farm profile, soil inputs, water budget, current rotation, priorities, constraints and field boundaries,
on top of M1's three registered demo locations: **Pamplemousses-04, Flacq-02, Black River-01**.

| File | What it does |
|---|---|
| `farm_profile.py` | Profile model, validation prompts, storage, `get_farm_profile()` for M4 |
| `soil_inputs.py` | Texture, pH, drainage with a source per value |
| `field_boundaries.py` | GeoJSON checks, area, centre, nearest M1 location, placeholder square, auto-outline stub |
| `units.py` | mm ↔ m³ water conversion |
| `routes.py` | `/api/farms` endpoints |

See `API_CONTRACT.md`. Run: `uvicorn app:app --reload` then open `/docs`.
