"""
FastAPI application entrypoint.

Phase 3 addition: registers the patients router alongside auth.

Verified additive-only (per Phase 3 review): this file has never defined
any middleware, exception handlers, or startup/shutdown events -- there
was nothing for the new router registration to overwrite. The auth
router registration from Phase 2 is untouched; `patients.router` is a
second, independent `include_router` call. Future phases (medications,
conditions, etc.) should follow the same pattern: one additional
`app.include_router(...)` line, never replacing an existing one.
"""
from fastapi import FastAPI

from app.api.v1 import auth, patients

app = FastAPI(title="Pharmacovigilance MVP API", version="0.1.0")

app.include_router(auth.router, prefix="/api/v1")
app.include_router(patients.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    """Basic liveness check, unrelated to auth -- useful for deployment probes."""
    return {"status": "ok"}
