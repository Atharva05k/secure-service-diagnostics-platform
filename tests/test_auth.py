
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app


TEST_API_KEY = "test-only-diagnostics-key"


@pytest.fixture
def client(monkeypatch):
    # Use a fictional API key during testing.
    monkeypatch.setenv(
        "DIAGNOSTICS_API_KEY",
        TEST_API_KEY,
    )

    # Simulate a database session without
    # connecting to PostgreSQL.
    fake_db = MagicMock()

    # GET /services should receive an empty list.
    fake_db.scalars.return_value.all.return_value = []

    def override_get_db():
        yield fake_db

    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override


def test_missing_api_key(client):
    response = client.get("/services")

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Invalid or missing API key"
    )


def test_invalid_api_key(client):
    response = client.get(
        "/services",
        headers={
            "X-API-Key": "incorrect-key",
        },
    )

    assert response.status_code == 401


def test_valid_api_key(client):
    response = client.get(
        "/services",
        headers={
            "X-API-Key": TEST_API_KEY,
        },
    )

    assert response.status_code == 200
    assert response.json() == []


def test_event_ingestion_requires_authentication(client):
    response = client.post(
        "/events",
        json={
            "service_id": 1,
            "event_type": "DIAGNOSTIC",
            "severity": "INFO",
            "message": "Authentication test",
        },
    )

    assert response.status_code == 401


def test_health_endpoint_is_public(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_missing_server_api_key_configuration(
    client,
    monkeypatch,
):
    monkeypatch.delenv(
        "DIAGNOSTICS_API_KEY",
        raising=False,
    )

    response = client.get(
        "/services",
        headers={
            "X-API-Key": TEST_API_KEY,
        },
    )

    assert response.status_code == 503
