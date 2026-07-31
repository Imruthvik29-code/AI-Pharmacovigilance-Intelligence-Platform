"""
FastAPI application entrypoint.

Phase 7 addition: registers the timeline router alongside auth, patients,
medications, conditions, and symptoms.

Verified additive-only (per Phase 7 review): this file has never defined
any middleware, exception handlers, or startup/shutdown events -- there
was nothing for the new router registration to overwrite. The auth,
patients, medications, conditions, and symptoms router registrations from
Phases 2-6 are untouched; timeline.router is a sixth, independent
`include_router` call. Future phases should follow the same pattern: one
additional `app.include_router(...)` line, never replacing an existing
one.
"""
from fastapi import FastAPI

from app.api.v1 import auth, conditions, medications, patients, symptoms, timeline

app = FastAPI(title="Pharmacovigilance MVP API", version="0.1.0")

app.include_router(auth.router, prefix="/api/v1")
app.include_router(patients.router, prefix="/api/v1")
app.include_router(medications.router, prefix="/api/v1")
app.include_router(conditions.router, prefix="/api/v1")
app.include_router(symptoms.router, prefix="/api/v1")
app.include_router(timeline.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    """Basic liveness check, unrelated to auth -- useful for deployment probes."""
    return {"status": "ok"}
