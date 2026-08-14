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
    Translate a Supabase Auth error response into our own sanitized API error.

    Never forwards the raw upstream JSON body to the client — only a short,
    sanitized message and a status code we choose. This avoids leaking
    upstream-specific structure/wording and keeps our API contract stable.

    Known Supabase Auth responses handled explicitly:
    - 400 / 422 with "already registered" / "user_already_exists" → 409
    - 429 with "over_email_send_rate_limit" / rate-limit → 429 (sanitized)
    - 400 / 401 / 422 with invalid credentials (login) → 401 generic
    - 400 / 422 validation errors (signup) → 400
    - 401 / other provider errors → 502

    The 429 handling is the only new status code vs. previous contract:
    previously 429 was incorrectly mapped to 502; now it correctly maps to
    429 Too Many Requests with a sanitized message.

    Logging of upstream status is done by callers (signup/login) via
    structured extra fields — no secrets, tokens, or raw upstream payloads
    are logged.
    """
    try:
        upstream = resp.json()
    except ValueError:
        upstream = {}

    upstream_msg = str(
        upstream.get("msg")
        or upstream.get("error_description")
        or upstream.get("error")
        or ""
    ).lower()

    upstream_code = str(
        upstream.get("error_code") or upstream.get("code") or ""
    ).lower()

    # -----------------------------------------------------------------
    # 429 — Rate limited (e.g., over_email_send_rate_limit)
    # -----------------------------------------------------------------
    # Supabase returns 429 when too many emails are sent (e.g., during
    # repeated signups). Previously this fell through to 502, which is
    # misleading. Return sanitized 429 instead.
    is_rate_limited = (
        resp.status_code == 429
        or "over_email_send_rate_limit" in upstream_msg
        or "over_email_send_rate_limit" in upstream_code
        or "rate_limit" in upstream_msg
        or "rate_limit" in upstream_code
    )
    if is_rate_limited:
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )

    # -----------------------------------------------------------------
    # Signup-specific handling
    # -----------------------------------------------------------------
    if context == "signup":
        if "already registered" in upstream_msg or "user_already_exists" in upstream_code:
            return HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists.",
            )

        if resp.status_code in (400, 422):
            # Validation errors — e.g., weak password, invalid email format
            return HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Signup request could not be completed.",
            )

        if resp.status_code == 401:
            # Invalid anon key or other unauthorized from Supabase — treat
            # as provider error to keep existing API contract (signup never
            # returned 401 before; it returned 502 for provider issues)
            return HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Authentication provider error. Please try again later.",
            )

    # -----------------------------------------------------------------
    # Login-specific handling
    # -----------------------------------------------------------------
    if context == "login":
        # Deliberately generic — do not reveal whether email exists.
        # Supabase may return 400 (invalid_grant), 401, or 422 for invalid
        # credentials — all map to same sanitized 401 to keep contract stable.
        if resp.status_code in (400, 401, 422):
            return HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )

    # -----------------------------------------------------------------
    # Fallback — explicit handling for remaining known codes while
    # preserving existing contract
    # -----------------------------------------------------------------
    if resp.status_code in (400, 422):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Signup request could not be completed.",
        )

    if resp.status_code == 401:
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication provider error. Please try again later.",
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
        # Structured logging — record upstream status without exposing
        # secrets or raw upstream payload (which may contain sensitive details).
        logger.warning(
            "signup_failed",
            extra={"email": payload.email, "upstream_status": resp.status_code},
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
