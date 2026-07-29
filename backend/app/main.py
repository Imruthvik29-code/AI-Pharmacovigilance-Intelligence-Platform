"""
FastAPI application entrypoint.

Note: no main.py was present in any of the reviewed repository documents
(Phase 1 was DB-schema-only, with no app process). This file was created
for that reason. If an existing main.py exists elsewhere in the repo that
wasn't part of the reviewed materials, merge the two lines below into it
instead of replacing it:
    from app.api.v1 import auth
    app.include_router(auth.router, prefix="/api/v1")
"""
from fastapi import FastAPI

from app.api.v1 import auth

app = FastAPI(title="Pharmacovigilance MVP API", version="0.1.0")

app.include_router(auth.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    """Basic liveness check, unrelated to auth -- useful for deployment probes."""
    return {"status": "ok"}
