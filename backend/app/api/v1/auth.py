"""
Authentication endpoints (spec section 7).

Signup/login are thin proxies to Supabase Auth's REST API -- Supabase owns
credential storage and token issuing (auth.users); this backend only
forwards the request and returns the session Supabase issues. This keeps
patients.user_id consistent with Supabase's own identity store without a
duplicate local users table.

Error handling: Supabase's raw error payloads are never forwarded to
clients (they can include upstream-specific wording/fields we don't want
to leak or couple to). `_map_supabase_error` translates them into our own
sanitized detail messages and status codes.

Logging: signup/login attempts and outcomes are logged for audit purposes.
Email addresses are logged (useful for tracing account issues); passwords
and tokens are never logged, in request bodies or responses.
"""
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.security import CurrentUser, get_current_user
from app.schemas.auth import AuthResponse, AuthUser, LoginRequest, SignupRequest

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
logger = logging.getLogger("app.auth")


def _supabase_headers() -> dict:
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server is not configured with Supabase URL/anon key.",
        )
    return {"apikey": settings.supabase_anon_key, "Content-Type": "application/json"}


def _to_auth_response(data: dict) -> AuthResponse:
    """Map Supabase's auth response shape onto our AuthResponse schema."""
    user = data.get("user") or {}
    return AuthResponse(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token"),
        expires_in=data.get("expires_in"),
        user=AuthUser(
            id=str(user.get("id", "")),
            email=str(user.get("email", "")),
        )
    )


def _map_supabase_error(resp: httpx.Response, context: str) -> HTTPException:
    """
    Translate a Supabase Auth error response into our own API error shape.

    Never forwards the raw upstream JSON body to the client -- only a
    short, sanitized message and a status code we choose ourselves. This
    avoids leaking upstream-specific error structure/wording and keeps our
    API contract stable even if Supabase changes its error format.
    """
    try:
        upstream = resp.json()
    except ValueError:
        upstream = {}

    upstream_msg = str(
        upstream.get("msg") or upstream.get("error_description") or upstream.get("error") or ""
    ).lower()

    if context == "signup" and "already registered" in upstream_msg:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    if context == "login":
        # Deliberately generic -- do not reveal whether the email exists.
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if resp.status_code in (400, 422):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Signup request could not be completed.",
        )

    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Authentication provider error. Please try again later.",
    )


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest):
    """Create a new Supabase Auth user and return the initial session."""
    logger.info("signup_attempt", extra={"email": payload.email})

    url = f"{settings.supabase_url}/auth/v1/signup"
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as http_client:
        try:
            resp = await http_client.post(
                url,
                headers=_supabase_headers(),
                json={"email": payload.email, "password": payload.password},
            )
        except httpx.RequestError as exc:
            logger.warning(
                "signup_upstream_unreachable", extra={"email": payload.email, "error": str(exc)}
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not reach the authentication provider.",
            )

    if resp.status_code >= 400:
        logger.warning(
            "signup_failed", extra={"email": payload.email, "upstream_status": resp.status_code}
        )
        raise _map_supabase_error(resp, context="signup")

    data = resp.json()
    if "access_token" not in data:
        # Supabase returns a user object with no session when email
        # confirmation is required. Surface that distinctly instead of
        # pretending a session was issued.
        logger.info("signup_pending_confirmation", extra={"email": payload.email})
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"detail": "Signup succeeded but requires email confirmation before login."},
        )

    logger.info("signup_succeeded", extra={"email": payload.email})
    return _to_auth_response(data)


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest) -> AuthResponse:
    """Exchange email/password for a Supabase session (access + refresh token)."""
    logger.info("login_attempt", extra={"email": payload.email})

    url = f"{settings.supabase_url}/auth/v1/token?grant_type=password"
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as http_client:
        try:
            resp = await http_client.post(
                url,
                headers=_supabase_headers(),
                json={"email": payload.email, "password": payload.password},
            )
        except httpx.RequestError as exc:
            logger.warning(
                "login_upstream_unreachable", extra={"email": payload.email, "error": str(exc)}
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not reach the authentication provider.",
            )

    if resp.status_code >= 400:
        logger.warning(
            "login_failed", extra={"email": payload.email, "upstream_status": resp.status_code}
        )
        raise _map_supabase_error(resp, context="login")

    logger.info("login_succeeded", extra={"email": payload.email})
    return _to_auth_response(resp.json())


@router.get("/me", response_model=AuthUser)
async def get_me(current_user: CurrentUser = Depends(get_current_user)) -> AuthUser:
    """
    Minimal protected route proving the JWT dependency works end-to-end.
    Not part of the frozen Section 7 contract list -- added as a thin,
    non-breaking verification endpoint for Phase 2's "Protected Routes" task.
    Real protected resources (patients, medications, etc.) start in Phase 3
    and will reuse `get_current_user` as-is.
    """
    return AuthUser(id=str(current_user.id), email=current_user.email)
