"""
FastAPI application entrypoint.

Phase 4 addition: registers the medications router alongside auth and
patients.

Verified additive-only (per Phase 4 review): this file has never defined
any middleware, exception handlers, or startup/shutdown events -- there
was nothing for the new router registration to overwrite. The auth and
patients router registrations from Phases 2-3 are untouched;
medications.router is a third, independent `include_router` call. Future
phases (conditions, symptoms, etc.) should follow the same pattern: one
additional `app.include_router(...)` line, never replacing an existing
one.
"""
from fastapi import FastAPI

from app.api.v1 import auth, medications, patients

app = FastAPI(title="Pharmacovigilance MVP API", version="0.1.0")

app.include_router(auth.router, prefix="/api/v1")
app.include_router(patients.router, prefix="/api/v1")
app.include_router(medications.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    """Basic liveness check, unrelated to auth -- useful for deployment probes."""
    return {"status": "ok"}
