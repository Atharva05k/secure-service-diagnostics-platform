from fastapi import FastAPI
from sqlalchemy import text

from app.database import engine
from app.routers.services import router as services_router
from app.routers.events import router as events_router


app = FastAPI(
    title="Secure Service Diagnostics & Reliability Platform",
    description=(
        "Backend platform for collecting service-health events, "
        "application errors, and diagnostic information."
    ),
    version="0.1.0",
)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "secure-service-diagnostics-platform",
    }

@app.get("/readiness")
def readiness_check():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    return {
        "status": "ready",
        "database": "connected",
    }
app.include_router(services_router)
app.include_router(events_router)