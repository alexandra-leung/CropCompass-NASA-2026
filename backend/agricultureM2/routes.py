
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .crop_catalog import load_crop_catalog
from .rotation_engine import evaluate_rotation
from .rotation_generator import (
    generate_rotation_candidates,
)
from .suitability import check_crop_suitability

router = APIRouter()


# -----------------------------------------
# Request Models
# -----------------------------------------

class RotationRequest(BaseModel):
    crops: list[str] = Field(
        min_length=2,
        max_length=12,
    )


class GenerateRotationRequest(BaseModel):
    current_rotation: list[str] = Field(
        min_length=2,
        max_length=6,
    )

    max_alternatives: int = Field(
        default=3,
        ge=1,
        le=20,
    )


# -----------------------------------------
# Crop Catalog
# -----------------------------------------

@router.get("/crops")
def get_crops():
    try:
        catalog = load_crop_catalog()

        return {
            "total": len(catalog),
            "crops": catalog.where(
                catalog.notna(), None
            ).to_dict(orient="records"),
        }

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )


# -----------------------------------------
# Rotation DNA
# -----------------------------------------

@router.post("/rotation")
def analyze_rotation(request: RotationRequest):
    try:
        return evaluate_rotation(request.crops)

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )


# -----------------------------------------
# Generate Alternative Rotations
# -----------------------------------------

@router.post("/generate")
def generate_rotations(
    request: GenerateRotationRequest,
):
    try:
        return generate_rotation_candidates(
            current_rotation=request.current_rotation,
            max_alternatives=request.max_alternatives,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )


# -----------------------------------------
# Crop Suitability
# -----------------------------------------

@router.get("/suitability/{crop_id}")
def crop_suitability(
    crop_id: str,
    temperature_c: float | None = None,
    soil_ph: float | None = None,
):
    try:
        return check_crop_suitability(
            crop_id=crop_id,
            temperature_c=temperature_c,
            soil_ph=soil_ph,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )
