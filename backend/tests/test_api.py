from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["service"] == "traffic-analysis-local-api"
        assert payload["contract_version"] == "feature-contract.v1"


def test_models_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/api/models")
        assert response.status_code == 200
        payload = response.json()
        assert payload["active_model_id"] == "mock-default"
        assert payload["items"]

