"""
JWT authentication utilities.

Verifies Supabase-issued JWTs against Supabase's published JWKS (JSON
Web Key Set) and exposes a FastAPI dependency that protected routes use
to get the current authenticated user's id. This module owns
verification only -- Supabase itself owns issuing tokens (see
api/v1/auth.py).

## Why JWKS instead of a shared secret

Supabase Auth signs access tokens asymmetrically. Confirmed directly
against this project's real, live-issued access tokens (not just
Supabase's general documentation) during this fix:
  - alg: ES256
  - aud: authenticated
  - iss: {SUPABASE_URL}/auth/v1
  - kid: present in this project's JWKS response

Verification therefore resolves the correct public key from Supabase's
JWKS endpoint (`{SUPABASE_URL}/auth/v1/.well-known/jwks.json`, via
`Settings.supabase_jwks_url`) using the token's `kid` header, rather than
a locally configured secret. `PyJWKClient` handles the fetch + key
matching, with an internal cache (`cache_keys=True` below) so most
requests never hit the network -- only a cache miss (e.g. an unrecognized
`kid` after Supabase rotates its signing key) triggers a refetch.

## Algorithm selection -- explicitly pinned to ES256

`algorithms=["ES256"]` is hardcoded rather than derived from the
matched JWK's own `alg` field. `jwt.decode` receives `signing_key.key`,
the raw public key from the resolved JWK, not the `PyJWK` object itself.
PyJWT therefore checks the token header's `alg` against this allow-list
and selects the ES256 verifier from that allowed header value; it does
not additionally enforce equality with the resolved JWK's own `alg`
metadata. The hardcoding makes the one algorithm this codebase accepts
explicit and auditable in code, instead of implicit in whatever
Supabase's JWKS response happens to declare. If Supabase ever migrates
off ES256, this line requires a deliberate, reviewed code change rather
than silently accepting a new algorithm.

## Dependency note

`pyjwt[crypto]>=2.13.0,<3.0.0` is required, not just `pyjwt[crypto]`.
PyJWT versions 2.9.0-2.12.1 have a known algorithm allow-list bypass
(CVE-2026-48523) when `jwt.decode` receives a `PyJWK`, fixed in 2.13.0.
This module instead passes the raw `signing_key.key` to `jwt.decode`, so
its current decode call does not use that CVE-affected `PyJWK` path. See
backend/requirements.txt.

## Issuer/audience validation

`aud` is validated as `"authenticated"`. `iss` is validated as
`{SUPABASE_URL}/auth/v1`. Both confirmed against this project's real
issued tokens.
"""
import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient, PyJWKClientError

from app.core.config import get_settings

settings = get_settings()

_bearer_scheme = HTTPBearer(auto_error=False)

# The one algorithm this codebase accepts for Supabase-issued access
# tokens. See module docstring's "Algorithm selection" section for why
# this is hardcoded rather than read from the resolved JWK.
_ALLOWED_ALGORITHMS = ["ES256"]

# Lazily created, module-level so PyJWKClient's internal key cache
# persists across requests within this process -- avoids refetching
# Supabase's JWKS on every single request. `None` until first use (or
# until reset, e.g. in tests); `_get_jwks_client` is the sole place that
# constructs it, so tests can monkeypatch that function directly instead
# of manipulating this module-level state.
_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    """Build (once) or return the cached PyJWKClient for Supabase's JWKS endpoint."""
    global _jwks_client
    if _jwks_client is None:
        if not settings.supabase_jwks_url:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Server is not configured with a Supabase URL.",
            )
        _jwks_client = PyJWKClient(settings.supabase_jwks_url, cache_keys=True)
    return _jwks_client


class CurrentUser:
    """Minimal authenticated-user context extracted from a verified JWT."""

    def __init__(self, id: uuid.UUID, email: str | None):
        self.id = id
        self.email = email


def decode_supabase_jwt(token: str) -> dict:
    """Decode and verify a Supabase-issued access token against Supabase's JWKS.

    Raises HTTPException(500) if the server itself has no configured
    Supabase URL (and therefore no JWKS endpoint to verify against).
    Raises HTTPException(401) if the token is missing, expired, malformed,
    signed by an unrecognized key, uses a disallowed algorithm, or fails
    audience/issuer validation.
    """
    jwks_client = _get_jwks_client()

    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=_ALLOWED_ALGORITHMS,
            audience="authenticated",
            issuer=f"{settings.supabase_url}/auth/v1",
            options={"require": ["exp", "aud", "iss"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired.",
        )
    except (PyJWKClientError, jwt.PyJWTError):
        # Covers: unknown/rotated `kid`, unreachable JWKS endpoint,
        # malformed token, bad signature, disallowed algorithm, wrong
        # audience/issuer -- all surfaced identically as an invalid
        # token, without leaking upstream fetch/verification details to
        # the client.
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

    try:
        user_id = uuid.UUID(sub)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token.",
        )

    return CurrentUser(
        id=user_id,
        email=payload.get("email"),
    )