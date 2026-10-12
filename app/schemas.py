from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ==========================================
# SERVICE REGISTRY SCHEMAS
# ==========================================

class ServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Service name cannot be blank")

        return value


class ServiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    created_at: datetime


# ==========================================
# DIAGNOSTIC EVENT SCHEMAS
# ==========================================

class EventType(str, Enum):
    HEALTH_CHECK = "HEALTH_CHECK"
    APPLICATION_ERROR = "APPLICATION_ERROR"
    DIAGNOSTIC = "DIAGNOSTIC"


class EventSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class EventCreate(BaseModel):
    service_id: int = Field(gt=0)

    event_type: EventType

    severity: EventSeverity

    message: str = Field(
        min_length=1,
        max_length=2000
    )

    details: dict[str, Any] | None = None

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Event message cannot be blank")

        return value


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    service_id: int
    event_type: EventType
    severity: EventSeverity
    message: str
    details: dict[str, Any] | None
    created_at: datetime