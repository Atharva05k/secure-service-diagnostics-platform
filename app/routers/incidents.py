from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.database import get_db
from app.schemas import (
    IncidentCreate,
    IncidentResponse,
    IncidentStatusUpdate,
)
from app.incident_services import (
    create_incident,
    list_incidents,
    get_incident_by_id,
    update_incident_status,
)


router = APIRouter(
    prefix="/incidents",
    tags=["Incidents"],
    dependencies=[Depends(require_api_key)],
)


@router.post(
    "",
    response_model=IncidentResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_incident(
    payload: IncidentCreate,
    db: Session = Depends(get_db),
):
    return create_incident(
        db=db,
        payload=payload,
    )


@router.get(
    "",
    response_model=list[IncidentResponse],
)
def read_incidents(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return list_incidents(
        db=db,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{incident_id}",
    response_model=IncidentResponse,
)
def read_incident(
    incident_id: int,
    db: Session = Depends(get_db),
):
    return get_incident_by_id(
        db=db,
        incident_id=incident_id,
    )


@router.patch(
    "/{incident_id}/status",
    response_model=IncidentResponse,
)
def change_incident_status(
    incident_id: int,
    payload: IncidentStatusUpdate,
    db: Session = Depends(get_db),
):
    return update_incident_status(
        db=db,
        incident_id=incident_id,
        payload=payload,
    )
