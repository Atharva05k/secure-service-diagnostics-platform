
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_db
from app.main import app
from app.models import (
    Service,
    DiagnosticEvent,
    Incident,
    IncidentAuditLog,
)


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

    def fake_flush():
        for recorded_call in fake_db.add.call_args_list:
            record = recorded_call.args[0]

            if isinstance(record, Incident) and record.id is None:
                record.id = 2
                record.created_at = fixed_time
                record.updated_at = fixed_time

    fake_db.flush.side_effect = fake_flush

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

    assert fake_db.add.call_count == 2

    saved_incident = fake_db.add.call_args_list[0].args[0]
    saved_audit = fake_db.add.call_args_list[1].args[0]

    assert isinstance(saved_audit, IncidentAuditLog)

    assert saved_audit.incident_id == saved_incident.id
    assert saved_audit.action == "INCIDENT_CREATED"
    assert saved_audit.previous_status is None
    assert saved_audit.new_status == "OPEN"
    assert saved_audit.actor_type == "SHARED_API_KEY"

    fake_db.flush.assert_called_once()


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

    audit = fake_db.add.call_args.args[0]

    assert isinstance(audit, IncidentAuditLog)
    assert audit.incident_id == 1
    assert audit.action == "STATUS_CHANGED"
    assert audit.previous_status == "OPEN"
    assert audit.new_status == "INVESTIGATING"


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

    audit = fake_db.add.call_args.args[0]

    assert isinstance(audit, IncidentAuditLog)
    assert audit.previous_status == "INVESTIGATING"
    assert audit.new_status == "RESOLVED"


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

    fake_db.add.assert_not_called()
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


def test_incident_creation_rolls_back_on_commit_failure(
    client_and_db,
):
    client, fake_db, _ = client_and_db

    # Simulate a database transaction failure.
    fake_db.commit.side_effect = SQLAlchemyError(
        "Simulated commit failure"
    )

    with pytest.raises(SQLAlchemyError):
        client.post(
            "/incidents",
            headers=HEADERS,
            json={
                "service_id": 1,
                "title": "Transaction failure test",
            },
        )

    # Both records were prepared for insertion.
    assert fake_db.add.call_count == 2

    # The application must roll back the transaction.
    fake_db.rollback.assert_called_once()


@pytest.fixture
def audit_entries():
    return [
        SimpleNamespace(
            id=101,
            incident_id=1,
            action="INCIDENT_CREATED",
            previous_status=None,
            new_status="OPEN",
            actor_type="SHARED_API_KEY",
            created_at=datetime(
                2026, 10, 13, 9, 0,
                tzinfo=timezone.utc,
            ),
        ),
        SimpleNamespace(
            id=102,
            incident_id=1,
            action="STATUS_CHANGED",
            previous_status="OPEN",
            new_status="INVESTIGATING",
            actor_type="SHARED_API_KEY",
            created_at=datetime(
                2026, 10, 13, 9, 5,
                tzinfo=timezone.utc,
            ),
        ),
        SimpleNamespace(
            id=103,
            incident_id=1,
            action="STATUS_CHANGED",
            previous_status="INVESTIGATING",
            new_status="RESOLVED",
            actor_type="SHARED_API_KEY",
            created_at=datetime(
                2026, 10, 13, 9, 15,
                tzinfo=timezone.utc,
            ),
        ),
    ]


def test_retrieve_complete_audit_history(
    client_and_db,
    audit_entries,
):
    client, fake_db, _ = client_and_db

    fake_db.scalars.return_value.all.return_value = (
        audit_entries
    )

    response = client.get(
        "/incidents/1/audit",
        headers=HEADERS,
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 3

    assert [
        entry["action"] for entry in data
    ] == [
        "INCIDENT_CREATED",
        "STATUS_CHANGED",
        "STATUS_CHANGED",
    ]

    assert [
        entry["new_status"] for entry in data
    ] == [
        "OPEN",
        "INVESTIGATING",
        "RESOLVED",
    ]

    assert data[0]["previous_status"] is None
    assert data[1]["previous_status"] == "OPEN"

    assert data[2]["previous_status"] == (
        "INVESTIGATING"
    )

    assert all(
        entry["incident_id"] == 1
        for entry in data
    )

    assert all(
        entry["actor_type"] == "SHARED_API_KEY"
        for entry in data
    )


def test_audit_history_query_filters_and_orders(
    client_and_db,
    audit_entries,
):
    client, fake_db, _ = client_and_db

    # Simulate the second record being returned
    # for limit=1 and offset=1.
    fake_db.scalars.return_value.all.return_value = [
        audit_entries[1]
    ]

    response = client.get(
        "/incidents/1/audit",
        headers=HEADERS,
        params={
            "limit": 1,
            "offset": 1,
        },
    )

    assert response.status_code == 200
    assert response.json()[0]["id"] == 102

    # Inspect the SQLAlchemy SELECT statement.
    statement = fake_db.scalars.call_args.args[0]

    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={
                "literal_binds": True,
            },
        )
    )

    # Normalize whitespace in the SQL string.
    sql = " ".join(sql.split())

    assert (
        "WHERE incident_audit_logs.incident_id = 1"
        in sql
    )

    assert (
        "ORDER BY incident_audit_logs.created_at ASC, "
        "incident_audit_logs.id ASC"
        in sql
    )

    assert "LIMIT 1 OFFSET 1" in sql


def test_existing_incident_without_audit_records(
    client_and_db,
):
    client, fake_db, _ = client_and_db

    fake_db.scalars.return_value.all.return_value = []

    response = client.get(
        "/incidents/1/audit",
        headers=HEADERS,
    )

    assert response.status_code == 200
    assert response.json() == []


def test_audit_history_for_nonexistent_incident(
    client_and_db,
):
    client, fake_db, _ = client_and_db

    response = client.get(
        "/incidents/999999/audit",
        headers=HEADERS,
    )

    assert response.status_code == 404

    assert response.json()["detail"] == (
        "Incident not found"
    )

    fake_db.scalars.assert_not_called()


def test_audit_history_requires_authentication(
    client_and_db,
):
    client, fake_db, _ = client_and_db

    response = client.get(
        "/incidents/1/audit",
    )

    assert response.status_code == 401

    fake_db.scalars.assert_not_called()


def test_audit_history_rejects_invalid_incident_id(
    client_and_db,
):
    client, fake_db, _ = client_and_db

    response = client.get(
        "/incidents/not-an-id/audit",
        headers=HEADERS,
    )

    assert response.status_code == 422
    fake_db.scalars.assert_not_called()


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
    ],
)
def test_audit_history_rejects_invalid_pagination(
    client_and_db,
    params,
):
    client, fake_db, _ = client_and_db

    response = client.get(
        "/incidents/1/audit",
        headers=HEADERS,
        params=params,
    )

    assert response.status_code == 422
    fake_db.scalars.assert_not_called()

def test_incident_creation_rolls_back_on_flush_failure(
    client_and_db,
):
    client, fake_db, _ = client_and_db

    fake_db.flush.side_effect = SQLAlchemyError(
        "Simulated flush failure"
    )

    with pytest.raises(SQLAlchemyError):
        client.post(
            "/incidents",
            headers=HEADERS,
            json={
                "service_id": 1,
                "title": "Flush failure test",
            },
        )

    # Only the incident is staged before flush fails.
    assert fake_db.add.call_count == 1

    fake_db.flush.assert_called_once()
    fake_db.commit.assert_not_called()
    fake_db.rollback.assert_called_once()


def test_status_update_rolls_back_on_commit_failure(
    client_and_db,
):
    client, fake_db, _ = client_and_db

    fake_db.commit.side_effect = SQLAlchemyError(
        "Simulated commit failure"
    )

    with pytest.raises(SQLAlchemyError):
        client.patch(
            "/incidents/1/status",
            headers=HEADERS,
            json={
                "status": "INVESTIGATING",
            },
        )

    # An audit record should have been staged.
    assert fake_db.add.call_count == 1

    audit_entry = fake_db.add.call_args.args[0]

    assert isinstance(
        audit_entry,
        IncidentAuditLog,
    )

    assert audit_entry.previous_status == "OPEN"
    assert audit_entry.new_status == "INVESTIGATING"

    fake_db.commit.assert_called_once()
    fake_db.rollback.assert_called_once()
