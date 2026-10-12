
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.database import get_db
from app.main import app
from app.models import Service, DiagnosticEvent, Incident


TEST_API_KEY = "test-only-incident-key"

HEADERS = {
    "X-API-Key": TEST_API_KEY,
}


@pytest.fixture
def client_and_db(monkeypatch):
    # Use a temporary API key instead of the real key.
    monkeypatch.setenv(
        "DIAGNOSTICS_API_KEY",
        TEST_API_KEY,
    )

    fake_db = MagicMock()

    fixed_time = datetime(
        2026, 10, 12,
        tzinfo=timezone.utc,
    )

    # Simulate a registered service.
    service = SimpleNamespace(id=1)

    # Simulate two diagnostic events.
    valid_event = SimpleNamespace(
        id=10,
        service_id=1,
    )

    wrong_service_event = SimpleNamespace(
        id=11,
        service_id=2,
    )

    # Simulate an existing incident.
    incident = SimpleNamespace(
        id=1,
        service_id=1,
        source_event_id=10,
        title="Payment database timeout",
        description="Repeated database connection errors",
        status="OPEN",
        created_at=fixed_time,
        updated_at=fixed_time,
        resolved_at=None,
    )

    def fake_get(model, record_id):
        if model is Service and record_id == 1:
            return service

        if model is DiagnosticEvent:
            if record_id == 10:
                return valid_event
            if record_id == 11:
                return wrong_service_event

        if model is Incident and record_id == 1:
            return incident

        return None

    fake_db.get.side_effect = fake_get

    fake_db.scalars.return_value.all.return_value = [
        incident
    ]

    # Simulate database-generated fields after insertion.
    def fake_refresh(record):
        if isinstance(record, Incident) and record.id is None:
            record.id = 2
            record.created_at = fixed_time
            record.updated_at = fixed_time

    fake_db.refresh.side_effect = fake_refresh

    def override_get_db():
        yield fake_db

    previous_override = app.dependency_overrides.get(
        get_db
    )

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            yield client, fake_db, incident
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = (
                previous_override
            )


# =========================================
# INCIDENT CREATION
# =========================================

def test_create_incident_sanitizes_sensitive_data(
    client_and_db,
):
    client, fake_db, _ = client_and_db

    response = client.post(
        "/incidents",
        headers=HEADERS,
        json={
            "service_id": 1,
            "source_event_id": 10,
            "title": "Issue for rahul@example.com",
            "description": "api_key=testIncidentSecret99",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["status"] == "OPEN"
    assert data["resolved_at"] is None

    assert "rahul@example.com" not in data["title"]
    assert "testIncidentSecret99" not in data["description"]

    # Verify the object passed to the database
    # already contains sanitized values.
    fake_db.add.assert_called_once()

    saved_incident = fake_db.add.call_args.args[0]

    assert isinstance(saved_incident, Incident)
    assert "[REDACTED_EMAIL]" in saved_incident.title
    assert "[REDACTED]" in saved_incident.description
    assert saved_incident.status == "OPEN"

    fake_db.commit.assert_called_once()


def test_create_incident_rejects_missing_service(
    client_and_db,
):
    client, fake_db, _ = client_and_db

    response = client.post(
        "/incidents",
        headers=HEADERS,
        json={
            "service_id": 999999,
            "title": "Unknown service incident",
        },
    )

    assert response.status_code == 404
    fake_db.add.assert_not_called()


def test_create_incident_rejects_missing_source_event(
    client_and_db,
):
    client, fake_db, _ = client_and_db

    response = client.post(
        "/incidents",
        headers=HEADERS,
        json={
            "service_id": 1,
            "source_event_id": 999999,
            "title": "Missing source event",
        },
    )

    assert response.status_code == 404
    fake_db.add.assert_not_called()


def test_create_incident_rejects_cross_service_event(
    client_and_db,
):
    client, fake_db, _ = client_and_db

    response = client.post(
        "/incidents",
        headers=HEADERS,
        json={
            "service_id": 1,
            "source_event_id": 11,
            "title": "Incorrect event association",
        },
    )

    assert response.status_code == 400
    fake_db.add.assert_not_called()


def test_create_incident_forbids_manual_status(
    client_and_db,
):
    client, fake_db, _ = client_and_db

    response = client.post(
        "/incidents",
        headers=HEADERS,
        json={
            "service_id": 1,
            "title": "Invalid initial state",
            "status": "RESOLVED",
        },
    )

    assert response.status_code == 422
    fake_db.add.assert_not_called()


# =========================================
# INCIDENT RETRIEVAL
# =========================================

def test_list_incidents_with_pagination(client_and_db):
    client, fake_db, _ = client_and_db

    response = client.get(
        "/incidents",
        headers=HEADERS,
        params={
            "limit": 1,
            "offset": 0,
        },
    )

    assert response.status_code == 200
    assert response.json()[0]["id"] == 1

    # Inspect the actual SQLAlchemy query.
    statement = fake_db.scalars.call_args.args[0]

    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={
                "literal_binds": True,
            },
        )
    )

    assert "LIMIT 1 OFFSET 0" in sql


def test_get_existing_incident(client_and_db):
    client, fake_db, _ = client_and_db

    response = client.get(
        "/incidents/1",
        headers=HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["id"] == 1
    assert response.json()["status"] == "OPEN"

    fake_db.get.assert_called_once_with(Incident, 1)


def test_get_missing_incident(client_and_db):
    client, _, _ = client_and_db

    response = client.get(
        "/incidents/999999",
        headers=HEADERS,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Incident not found"


# =========================================
# VALID STATUS TRANSITIONS
# =========================================

def test_open_to_investigating(client_and_db):
    client, fake_db, incident = client_and_db

    response = client.patch(
        "/incidents/1/status",
        headers=HEADERS,
        json={
            "status": "INVESTIGATING",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "INVESTIGATING"
    assert response.json()["resolved_at"] is None

    assert incident.status == "INVESTIGATING"
    fake_db.commit.assert_called_once()


def test_investigating_to_resolved(client_and_db):
    client, fake_db, incident = client_and_db

    incident.status = "INVESTIGATING"

    before_update = datetime.now(timezone.utc)

    response = client.patch(
        "/incidents/1/status",
        headers=HEADERS,
        json={
            "status": "RESOLVED",
        },
    )

    after_update = datetime.now(timezone.utc)

    assert response.status_code == 200
    assert response.json()["status"] == "RESOLVED"

    assert incident.status == "RESOLVED"
    assert incident.resolved_at is not None

    assert (
        before_update
        <= incident.resolved_at
        <= after_update
    )

    fake_db.commit.assert_called_once()


# =========================================
# INVALID STATUS TRANSITIONS
# =========================================

@pytest.mark.parametrize(
    "current_status, requested_status",
    [
        ("OPEN", "RESOLVED"),
        ("INVESTIGATING", "INVESTIGATING"),
        ("RESOLVED", "INVESTIGATING"),
    ],
)
def test_invalid_status_transitions(
    client_and_db,
    current_status,
    requested_status,
):
    client, fake_db, incident = client_and_db

    incident.status = current_status

    response = client.patch(
        "/incidents/1/status",
        headers=HEADERS,
        json={
            "status": requested_status,
        },
    )

    assert response.status_code == 409

    # Rejected updates must not modify the record.
    assert incident.status == current_status

    fake_db.commit.assert_not_called()


def test_update_missing_incident(client_and_db):
    client, fake_db, _ = client_and_db

    response = client.patch(
        "/incidents/999999/status",
        headers=HEADERS,
        json={
            "status": "INVESTIGATING",
        },
    )

    assert response.status_code == 404
    fake_db.commit.assert_not_called()


# =========================================
# AUTHENTICATION AND VALIDATION
# =========================================

@pytest.mark.parametrize(
    "method, path, body",
    [
        ("GET", "/incidents", None),
        (
            "POST",
            "/incidents",
            {
                "service_id": 1,
                "title": "Authentication test",
            },
        ),
        (
            "PATCH",
            "/incidents/1/status",
            {
                "status": "INVESTIGATING",
            },
        ),
    ],
)
def test_incident_endpoints_require_authentication(
    client_and_db,
    method,
    path,
    body,
):
    client, _, _ = client_and_db

    response = client.request(
        method,
        path,
        json=body,
    )

    assert response.status_code == 401


def test_invalid_incident_status_value(client_and_db):
    client, fake_db, _ = client_and_db

    response = client.patch(
        "/incidents/1/status",
        headers=HEADERS,
        json={
            "status": "PAUSED",
        },
    )

    assert response.status_code == 422
    fake_db.commit.assert_not_called()


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 101},
        {"offset": -1},
    ],
)
def test_invalid_incident_pagination(
    client_and_db,
    params,
):
    client, fake_db, _ = client_and_db

    response = client.get(
        "/incidents",
        headers=HEADERS,
        params=params,
    )

    assert response.status_code == 422
    fake_db.scalars.assert_not_called()
