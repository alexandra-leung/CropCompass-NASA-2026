from fastapi.testclient import TestClient

from app import app


def test_crop_catalog_endpoint_returns_serializable_json():
    response = TestClient(app).get("/api/agriculture/crops")

    assert response.status_code == 200
    assert response.json()["total"] > 0
