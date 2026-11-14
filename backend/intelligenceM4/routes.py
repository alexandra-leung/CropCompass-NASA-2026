"""
M4 HTTP routes. Prefix lives here (like M1), so app.py only needs
`app.include_router(intelligence_router)`.

Endpoints are added phase by phase:
  Phase 2  POST /api/intelligence/evidence
  Phase 3  POST /api/intelligence/blind-spots
  Phase 4  POST /api/intelligence/assistant
  Phase 5  POST /api/intelligence/analyze
"""

from fastapi import APIRouter

router = APIRouter(
    prefix="/api/intelligence",
    tags=["M4 - Explainable AI & Integration"],
)
