from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    EventCreate,
    EventResponse,
    EventSeverity,
    EventType,
)
from app.event_services import(
    create_diagnostic_event,
    list_diagnostic_events,
    get_diagnostic_event_by_id,
)
from app.auth import require_api_key

router = APIRouter(
    prefix="/events",
    tags=["Diagnostic Events"],
    dependencies=[Depends(require_api_key)],
)


@router.post(
    "",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_diagnostic_event(
    payload: EventCreate,
    db: Session = Depends(get_db),
):
    return create_diagnostic_event(db, payload)

@router.get(
    "",
    response_model=list[EventResponse],
)
def read_diagnostic_events(
    service_id: int | None = Query(default=None, gt=0),
    severity: EventSeverity | None = Query(default=None),
    event_type: EventType | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return list_diagnostic_events(
        db=db,
        limit=limit,
        offset=offset,
        service_id=service_id,
        severity=severity,
        event_type=event_type,
    )

@router.get(
    "/{event_id}",
    response_model=EventResponse,
)
def read_diagnostic_event(
    event_id: int,
    db: Session = Depends(get_db),
):
    return get_diagnostic_event_by_id(
        db=db,
        event_id=event_id,
    )