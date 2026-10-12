from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import EventCreate, EventResponse
from app.event_services import create_diagnostic_event


router = APIRouter(
    prefix="/events",
    tags=["Diagnostic Events"],
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