
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.database import get_db
from app.main import app
from app.models import DiagnosticEvent


TEST_API_KEY = "test-only-event-retrieval-key"

HEADERS = {
    "X-API-Key": TEST_API_KEY,
}


@pytest.fixture
def client_and_db(monkeypatch):
    # Set a temporary API key for this test.
    monkeypatch.setenv(
        "DIAGNOSTICS_API_KEY",
        TEST_API_KEY,
    )

    # Create a simulated database session.
    fake_db = MagicMock()

    # Simulate one previously sanitized event.
    stored_event = SimpleNamespace(
        id=1,
        service_id=1,
        event_type="APPLICATION_ERROR",
        severity="ERROR",
        message="Payment failed for [REDACTED_EMAIL]",
        details={
            "customer_email": "[REDACTED]",
            "error_code": "PAYMENT_TIMEOUT",
        },
        created_at=datetime(
            2026, 10, 12,
            tzinfo=timezone.utc,
        ),
    )

    # Simulate SQLAlchemy query results.
    fake_db.scalars.return_value.all.return_value = [
        stored_event
    ]

    # Simulate primary-key lookup.
    fake_db.get.return_value = stored_event

    def override_get_db():
        yield fake_db

    # Preserve any existing dependency override.
    previous_override = app.dependency_overrides.get(get_db)

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client, fake_db
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override


def compiled_sql(fake_db):
    statement = fake_db.scalars.call_args.args[0]

    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


# ---------------------------------------
# EVENT LISTING
# ---------------------------------------

def test_list_events(client_and_db):
    client, fake_db = client_and_db

    response = client.get(
        "/events",
        headers=HEADERS,
    )

    assert response.status_code == 200
    assert len(response.json()) == 1

    event = response.json()[0]

    assert event["id"] == 1
    assert event["severity"] == "ERROR"
    assert "[REDACTED_EMAIL]" in event["message"]

    sql = compiled_sql(fake_db)

    assert "LIMIT 20 OFFSET 0" in sql


def test_list_events_requires_authentication(client_and_db):
    client, fake_db = client_and_db

    response = client.get("/events")

    assert response.status_code == 401
    fake_db.scalars.assert_not_called()


# ---------------------------------------
# EVENT FILTERING
# ---------------------------------------

@pytest.mark.parametrize(
    "params, expected_sql",
    [
        (
            {"service_id": 1},
            "diagnostic_events.service_id = 1",
        ),
        (
            {"severity": "ERROR"},
            "diagnostic_events.severity = 'ERROR'",
        ),
        (
            {"event_type": "APPLICATION_ERROR"},
            "diagnostic_events.event_type = 'APPLICATION_ERROR'",
        ),
    ],
)
def test_individual_filters(
    client_and_db,
    params,
    expected_sql,
):
    client, fake_db = client_and_db

    response = client.get(
        "/events",
        headers=HEADERS,
        params=params,
    )

    assert response.status_code == 200

    sql = compiled_sql(fake_db)

    assert expected_sql in sql


def test_combined_filters_and_pagination(client_and_db):
    client, fake_db = client_and_db

    response = client.get(
        "/events",
        headers=HEADERS,
        params={
            "service_id": 1,
            "severity": "ERROR",
            "event_type": "APPLICATION_ERROR",
            "limit": 2,
            "offset": 1,
        },
    )

    assert response.status_code == 200

    sql = compiled_sql(fake_db)

    assert "diagnostic_events.service_id = 1" in sql
    assert "diagnostic_events.severity = 'ERROR'" in sql
    assert (
        "diagnostic_events.event_type = 'APPLICATION_ERROR'"
        in sql
    )

    assert "LIMIT 2 OFFSET 1" in sql

    assert (
        "ORDER BY diagnostic_events.created_at DESC, "
        "diagnostic_events.id DESC"
    ) in sql


# ---------------------------------------
# INDIVIDUAL EVENT RETRIEVAL
# ---------------------------------------

def test_get_existing_event(client_and_db):
    client, fake_db = client_and_db

    response = client.get(
        "/events/1",
        headers=HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["id"] == 1
    assert response.json()["message"] == (
        "Payment failed for [REDACTED_EMAIL]"
    )

    fake_db.get.assert_called_once_with(
        DiagnosticEvent,
        1,
    )


def test_get_missing_event(client_and_db):
    client, fake_db = client_and_db

    fake_db.get.return_value = None

    response = client.get(
        "/events/999999",
        headers=HEADERS,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Diagnostic event not found"
    )


def test_get_event_requires_authentication(client_and_db):
    client, fake_db = client_and_db

    response = client.get("/events/1")

    assert response.status_code == 401
    fake_db.get.assert_not_called()


# ---------------------------------------
# REQUEST VALIDATION
# ---------------------------------------

@pytest.mark.parametrize(
    "params",
    [
        {"limit": 101},
        {"offset": -1},
        {"severity": "EXTREME"},
        {"service_id": 0},
    ],
)
def test_invalid_query_parameters(client_and_db, params):
    client, fake_db = client_and_db

    response = client.get(
        "/events",
        headers=HEADERS,
        params=params,
    )

    assert response.status_code == 422
    fake_db.scalars.assert_not_called()


def test_invalid_event_id(client_and_db):
    client, fake_db = client_and_db

    response = client.get(
        "/events/abc",
        headers=HEADERS,
    )

    assert response.status_code == 422
    fake_db.get.assert_not_called()
