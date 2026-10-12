from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Service, DiagnosticEvent
from app.schemas import EventCreate
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