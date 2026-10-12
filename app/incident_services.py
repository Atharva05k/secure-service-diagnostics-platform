
from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Service, DiagnosticEvent, Incident
from app.schemas import (
    IncidentCreate,
    IncidentStatusUpdate,
)
from app.sanitization import sanitize_text
from sqlalchemy import select
from datetime import datetime, timezone


def create_incident(
    db: Session,
    payload: IncidentCreate,
) -> Incident:

    # Step 1: Verify that the service exists.
    service = db.get(Service, payload.service_id)

    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found",
        )

    # Step 2: Verify the optional diagnostic event.
    if payload.source_event_id is not None:
        source_event = db.get(
            DiagnosticEvent,
            payload.source_event_id,
        )

        if source_event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Source diagnostic event not found",
            )

        if source_event.service_id != payload.service_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source event does not belong to this service",
            )

    # Step 3: Sanitize user-supplied text.
    sanitized_title = sanitize_text(payload.title)

    sanitized_description = (
        sanitize_text(payload.description)
        if payload.description is not None
        else None
    )

    # Ensure sanitization does not exceed the DB title limit.
    if len(sanitized_title) > 200:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Sanitized incident title exceeds 200 characters",
        )

    # Step 4: Create the database object.
    incident = Incident(
        service_id=payload.service_id,
        source_event_id=payload.source_event_id,
        title=sanitized_title,
        description=sanitized_description,
        status="OPEN",
    )

    # Step 5: Save the incident.
    db.add(incident)

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    db.refresh(incident)

    return incident



def list_incidents(
    db: Session,
    limit: int,
    offset: int,
) -> list[Incident]:

    statement = (
        select(Incident)
        .order_by(
            Incident.created_at.desc(),
            Incident.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )

    incidents = db.scalars(statement).all()

    return list(incidents)


def update_incident_status(
    db: Session,
    incident_id: int,
    payload: IncidentStatusUpdate,
) -> Incident:

    # Step 1: Retrieve the incident.
    incident = db.get(Incident, incident_id)

    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        )

    # Step 2: Define permitted transitions.
    allowed_transitions = {
        "OPEN": "INVESTIGATING",
        "INVESTIGATING": "RESOLVED",
    }

    current_status = incident.status
    requested_status = payload.status.value

    expected_next_status = allowed_transitions.get(
        current_status
    )

    # Step 3: Reject invalid transitions.
    if requested_status != expected_next_status:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot transition incident from "
                f"{current_status} to {requested_status}"
            ),
        )

    # Step 4: Update the status.
    incident.status = requested_status

    # Step 5: Record the resolution timestamp.
    if requested_status == "RESOLVED":
        incident.resolved_at = datetime.now(timezone.utc)

    # Step 6: Commit the change.
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    db.refresh(incident)

    return incident


def get_incident_by_id(
    db: Session,
    incident_id: int,
) -> Incident:

    incident = db.get(Incident, incident_id)

    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        )

    return incident