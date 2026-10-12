from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import ServiceCreate, ServiceResponse
from app.services import (
    create_service,
    list_services,
    get_service_by_id,
)
from app.auth import require_api_key


router = APIRouter(
    prefix="/services",
    tags=["Services"],
    dependencies=[Depends(require_api_key)],
)


@router.post(
    "",
    response_model=ServiceResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_service(
    payload: ServiceCreate,
    db: Session = Depends(get_db),
):
    return create_service(db, payload)


@router.get(
    "",
    response_model=list[ServiceResponse],
)
def read_services(
    db: Session = Depends(get_db),
):
    return list_services(db)


@router.get(
    "/{service_id}",
    response_model=ServiceResponse,
)
def read_service(
    service_id: int,
    db: Session = Depends(get_db),
):
    return get_service_by_id(db, service_id)