"""
FastAPI application entrypoint.

Phase 14 addition: registers the analysis router alongside auth,
patients, medications, conditions, symptoms, timeline, and schedule.

Reference-drug search addition: registers the reference_drugs router
(GET /reference-drugs/search -- read-only catalog search, supports the
RxNorm-expanded catalog). Additive-only, same pattern as every prior
router registration.

Verified additive-only (per Phase 14 review, following the same pattern
as every prior phase's registration): this file has never defined any
middleware, exception handlers, or startup/shutdown events -- there was
nothing for the new router registration to overwrite. All prior router
registrations from Phases 2-9 are untouched; analysis.router is an
eighth, independent `include_router` call. Future phases should follow
the same pattern: one additional `app.include_router(...)` line, never
replacing an existing one.
"""
from fastapi import FastAPI

from app.api.v1 import (
    analysis,
    auth,
    conditions,
    medications,
    patients,
    reference_drugs,
    schedule,
    symptoms,
    timeline,
)

app = FastAPI(title="Pharmacovigilance MVP API", version="0.1.0")

app.include_router(auth.router, prefix="/api/v1")
app.include_router(patients.router, prefix="/api/v1")
app.include_router(medications.router, prefix="/api/v1")
app.include_router(conditions.router, prefix="/api/v1")
app.include_router(symptoms.router, prefix="/api/v1")
app.include_router(timeline.router, prefix="/api/v1")
app.include_router(schedule.router, prefix="/api/v1")
app.include_router(analysis.router, prefix="/api/v1")
app.include_router(reference_drugs.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    """Basic liveness check, unrelated to auth -- useful for deployment probes."""
    return {"status": "ok"}
