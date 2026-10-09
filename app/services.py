from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Service
from app.schemas import ServiceCreate


def create_service(db: Session, payload: ServiceCreate) -> Service:
    service = Service(
        name=payload.name,
        description=payload.description,
    )

    db.add(service)

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A service with this name already exists",
        ) from None

    db.refresh(service)

    return service


def list_services(db: Session) -> list[Service]:
    statement = select(Service).order_by(Service.id)

    services = db.scalars(statement).all()

    return list(services)


def get_service_by_id(
    db: Session,
    service_id: int,
) -> Service:

    service = db.get(Service, service_id)

    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found",
        )

    return service