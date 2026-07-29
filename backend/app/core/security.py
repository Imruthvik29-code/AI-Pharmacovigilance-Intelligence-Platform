"""
JWT authentication utilities.

Verifies Supabase-issued JWTs (HS256, signed with the project's JWT secret)
and exposes a FastAPI dependency that protected routes use to get the
current authenticated user's id. This module owns verification only --
Supabase itself owns issuing tokens (see api/v1/auth.py).
"""
import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

settings = get_settings()

_bearer_scheme = HTTPBearer(auto_error=False)


class CurrentUser:
    """Minimal authenticated-user context extracted from a verified JWT."""

    def __init__(self, id: uuid.UUID, email: str | None):
        self.id = id
        self.email = email


def decode_supabase_jwt(token: str) -> dict:
    """Decode and verify a Supabase-issued access token.

    Raises HTTPException(401) if the token is missing, expired, or invalid.
    """
    if not settings.supabase_jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server is not configured with a Supabase JWT secret.",
        )
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired.",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token.",
        )
    return payload


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    """FastAPI dependency: verifies the bearer token and returns the caller.

    Attach this to any route that must be protected, e.g.:
        @router.get("/patients")
        async def list_patients(user: CurrentUser = Depends(get_current_user)):
            ...
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_supabase_jwt(credentials.credentials)

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim.",
        )

    return CurrentUser(id=uuid.UUID(sub), email=payload.get("email"))
