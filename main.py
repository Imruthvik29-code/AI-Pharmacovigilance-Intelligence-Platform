"""
FastAPI application entrypoint.

Phase 3 addition: registers the patients router alongside auth. No other
changes to this file's structure/behavior from Phase 2.
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
