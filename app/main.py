from fastapi import FastAPI


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