"""
M4 HTTP routes. Prefix lives here (like M1), so app.py only needs to include
this router.

Endpoints are added phase by phase:
  Phase 2  POST /api/intelligence/evidence      (live)
  Phase 3  POST /api/intelligence/blind-spots
  Phase 4  POST /api/intelligence/assistant
  Phase 5  POST /api/intelligence/analyze
"""

from fastapi import APIRouter, HTTPException

from intelligenceM4.evidence_passport import TraceabilityError, build_passport
from intelligenceM4.schemas import AnalysisBundle, EvidencePassport

router = APIRouter(
    prefix="/api/intelligence",
    tags=["M4 - Explainable AI & Integration"],
)


@router.post(
    "/evidence",
    response_model=EvidencePassport,
    summary="Build the Evidence Passport for a supplied analysis",
    description=(
        "Deterministically cites the M1/M2/M3/M5 results in the supplied "
        "AnalysisBundle. Every upstream value carries the exact field_path it "
        "was copied from. Missing data is reported, never filled in."
    ),
)
def evidence(bundle: AnalysisBundle) -> EvidencePassport:
    try:
        return build_passport(bundle)
    except TraceabilityError as exc:
        raise HTTPException(status_code=500, detail=f"Evidence traceability check failed: {exc}")
