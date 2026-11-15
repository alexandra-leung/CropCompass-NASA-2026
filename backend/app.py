
from fastapi import FastAPI
from climateM1.api.climate import router as climate_router
from agricultureM2.routes import router as agriculture_router
from agricultureM2.plans_routes import router as plans_router
from intelligenceM4.routes import router as intelligence_router
from mappingM3.routes import router as mapping_router
from resilienceM5.m1_adapter import provide_m1_climate
from resilienceM5.m2_adapter import evaluate_m2_scenario
from resilienceM5.routes import router as resilience_router
from resilienceM5.scenario_engine import register_m1_provider
from resilienceM5.stress_test import register_m2_evaluator

app = FastAPI(
    title="CropCompass 2.0",
    description="NASA Space Apps Challenge 2026",
    version="1.0.0"
)

register_m1_provider(provide_m1_climate)
register_m2_evaluator(evaluate_m2_scenario)

# M1 - Climate Intelligence
app.include_router(climate_router)

# M2 - Agricultural Intelligence
app.include_router(
    agriculture_router,
    prefix="/api/agriculture",
    tags=["M2 - Agricultural Intelligence"],
)
# M2 - ranked plans (water need, suitability, score)
app.include_router(plans_router)

# M3 - Farm Mapping
app.include_router(mapping_router)

app.include_router(intelligence_router)

# M5 - Climate Resilience
app.include_router(resilience_router)

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


