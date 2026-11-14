
from fastapi import FastAPI

app = FastAPI(
    title="CropCompass 2.0",
    description="NASA Space Apps Challenge 2026",
    version="1.0.0"
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
