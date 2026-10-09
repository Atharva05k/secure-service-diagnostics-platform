from fastapi import FastAPI
from sqlalchemy import text

from app.database import engine


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