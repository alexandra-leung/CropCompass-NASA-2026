
from fastapi import FastAPI
from climateM1.api.climate import router as climate_router
from agricultureM2.routes import router as agriculture_router

app = FastAPI(
    title="CropCompass 2.0",
    description="NASA Space Apps Challenge 2026",
    version="1.0.0"
)

# M1 - Climate Intelligence
app.include_router(climate_router)

# M2 - Agricultural Intelligence
app.include_router(
    agriculture_router,
    prefix="/api/agriculture",
    tags=["M2 - Agricultural Intelligence"],
)

@app.get("/")
def root():
    return {
        "project": "CropCompass 2.0",
        "status": "running",
        "team": "Marigold"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }


