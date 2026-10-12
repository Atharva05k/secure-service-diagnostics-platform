from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import Service, DiagnosticEvent
from app.schemas import EventCreate, EventSeverity, EventType
from app.sanitization import sanitize_text, sanitize_data


def create_diagnostic_event(
    db: Session,
    payload: EventCreate,
) -> DiagnosticEvent:

    # Step 1: Verify the registered service exists
    service = db.get(Service, payload.service_id)

    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found",
        )

    # Step 2: Sanitize sensitive data before storage
    sanitized_message = sanitize_text(payload.message)

    sanitized_details = (
        sanitize_data(payload.details)
        if payload.details is not None
        else None
    )

    # Step 3: Build the database object
    event = DiagnosticEvent(
        service_id=payload.service_id,
        event_type=payload.event_type.value,
        severity=payload.severity.value,
        message=sanitized_message,
        details=sanitized_details,
    )

    # Step 4: Persist the sanitized event
    db.add(event)
    db.commit()
    db.refresh(event)

    return event

def list_diagnostic_events(
    db: Session,
    limit: int,
    offset: int,
    service_id: int | None = None,
    severity: EventSeverity | None = None,
    event_type: EventType | None = None,
) -> list[DiagnosticEvent]:

    statement = select(DiagnosticEvent)

    # Filter by registered service
    if service_id is not None:
        statement = statement.where(
            DiagnosticEvent.service_id == service_id
        )

    # Filter by event severity
    if severity is not None:
        statement = statement.where(
            DiagnosticEvent.severity == severity.value
        )

    # Filter by event type
    if event_type is not None:
        statement = statement.where(
            DiagnosticEvent.event_type == event_type.value
        )

    # Sort newest first and apply pagination
    statement = (
        statement
        .order_by(
            DiagnosticEvent.created_at.desc(),
            DiagnosticEvent.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )

    events = db.scalars(statement).all()

    return list(events)

def get_diagnostic_event_by_id(
    db: Session,
    event_id: int,
) -> DiagnosticEvent:

    event = db.get(DiagnosticEvent, event_id)

    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diagnostic event not found",
        )

    return event