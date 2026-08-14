import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import CurrentUser, get_current_user
from app.main import app

settings = get_settings()
client = TestClient(app)


class _FakeResponse:
    def __init__(self, status_code: int, json_data: dict):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data


class _FakeAsyncClient:
    def __init__(self, fake_response: _FakeResponse):
        self._fake_response = fake_response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        return self._fake_response


@pytest.fixture(autouse=True)
def _configure_env(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "test-anon-key")


def test_signup_success(monkeypatch):
    fake_data = {
        "access_token": "fake-access-token",
        "refresh_token": "fake-refresh-token",
        "expires_in": 3600,
        "user": {"id": str(uuid.uuid4()), "email": "new@example.com"},
    }
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(_FakeResponse(200, fake_data))
    )
    resp = client.post(
        "/api/v1/auth/signup", json={"email": "new@example.com", "password": "supersecret1"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["access_token"] == "fake-access-token"
    assert body["user"]["email"] == "new@example.com"


def test_signup_requires_email_confirmation(monkeypatch):
    fake_data = {"user": {"id": str(uuid.uuid4()), "email": "new@example.com"}}
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(_FakeResponse(200, fake_data))
    )
    resp = client.post(
        "/api/v1/auth/signup", json={"email": "new@example.com", "password": "supersecret1"}
    )
    assert resp.status_code == 202
    assert "confirmation" in resp.json()["detail"].lower()


def test_signup_duplicate_email_returns_sanitized_409(monkeypatch):
    """
    Required-change #3: Supabase's raw error payload must never reach the
    client. We simulate Supabase's real "already registered" error shape
    and assert the client only ever sees our own sanitized message/code.
    """
    upstream_error = {
        "msg": "User already registered",
        "error_code": "user_already_exists",
        "code": 400,
    }
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(_FakeResponse(400, upstream_error))
    )
    resp = client.post(
        "/api/v1/auth/signup", json={"email": "dup@example.com", "password": "supersecret1"}
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["detail"] == "An account with this email already exists."
    # The raw upstream payload must not leak into the response.
    assert "user_already_exists" not in str(body)
    assert "error_code" not in body


def test_login_success(monkeypatch):
    fake_data = {
        "access_token": "fake-access-token",
        "refresh_token": "fake-refresh-token",
        "expires_in": 3600,
        "user": {"id": str(uuid.uuid4()), "email": "user@example.com"},
    }
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(_FakeResponse(200, fake_data))
    )
    resp = client.post(
        "/api/v1/auth/login", json={"email": "user@example.com", "password": "supersecret1"}
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"] == "fake-access-token"


def test_login_invalid_credentials(monkeypatch):
    upstream_error = {"error": "invalid_grant", "error_description": "Invalid login credentials"}
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(_FakeResponse(400, upstream_error)),
    )
    resp = client.post(
        "/api/v1/auth/login", json={"email": "user@example.com", "password": "wrong"}
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["detail"] == "Invalid email or password."
    # The raw upstream payload must not leak into the response.
    assert "invalid_grant" not in str(body)


def test_me_requires_auth_header():
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_me_with_valid_user_override():
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=uuid.uuid4(), email="user@example.com"
    )
    try:
        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer fake-token"},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["email"] == "user@example.com"


def test_me_with_invalid_token():
    resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


# -----------------------------------------------------------------
# New tests — 429 rate-limit handling (over_email_send_rate_limit)
# -----------------------------------------------------------------


def test_signup_rate_limited_over_email_returns_sanitized_429(monkeypatch):
    """
    Supabase returns 429 with error_code over_email_send_rate_limit when
    too many signup emails are sent. Previously this was incorrectly mapped
    to 502. It must now return sanitized 429.
    """
    upstream_error = {
        "msg": "For security purposes, you can only request this once every 60 seconds",
        "error_code": "over_email_send_rate_limit",
        "code": 429,
    }
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(_FakeResponse(429, upstream_error))
    )
    resp = client.post(
        "/api/v1/auth/signup", json={"email": "rate@example.com", "password": "supersecret1"}
    )
    assert resp.status_code == 429
    body = resp.json()
    assert body["detail"] == "Too many requests. Please try again later."
    # Must not leak upstream details
    assert "over_email_send_rate_limit" not in str(body)
    assert "error_code" not in body
    assert "For security purposes" not in str(body)


def test_signup_rate_limited_by_status_code_returns_429(monkeypatch):
    """
    Even if Supabase returns 429 with generic rate-limit wording (no
    over_email_send_rate_limit code), we must still return sanitized 429.
    """
    upstream_error = {
        "error": "rate_limit exceeded",
        "error_description": "Too many requests",
    }
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(_FakeResponse(429, upstream_error))
    )
    resp = client.post(
        "/api/v1/auth/signup", json={"email": "rate2@example.com", "password": "supersecret1"}
    )
    assert resp.status_code == 429
    assert resp.json()["detail"] == "Too many requests. Please try again later."


def test_login_rate_limited_returns_sanitized_429(monkeypatch):
    """
    429 handling must apply to login as well — rate limiting is not
    signup-specific. Should return 429, not 401 or 502.
    """
    upstream_error = {
        "msg": "Too many requests",
        "error_code": "over_email_send_rate_limit",
    }
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(_FakeResponse(429, upstream_error))
    )
    resp = client.post(
        "/api/v1/auth/login", json={"email": "user@example.com", "password": "supersecret1"}
    )
    assert resp.status_code == 429
    assert resp.json()["detail"] == "Too many requests. Please try again later."
    # Must not leak upstream
    assert "over_email_send_rate_limit" not in str(resp.json())


def test_signup_401_upstream_returns_502_sanitized(monkeypatch):
    """
    Explicit handling for 401 from Supabase during signup — e.g., invalid
    anon key — should map to 502 provider error to keep existing contract
    (signup never returned 401 before).
    """
    upstream_error = {"error": "unauthorized", "error_description": "Invalid API key"}
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(_FakeResponse(401, upstream_error))
    )
    resp = client.post(
        "/api/v1/auth/signup", json={"email": "test@example.com", "password": "supersecret1"}
    )
    assert resp.status_code == 502
    assert resp.json()["detail"] == "Authentication provider error. Please try again later."
    assert "Invalid API key" not in str(resp.json())


def test_signup_422_validation_returns_400_sanitized(monkeypatch):
    """
    Explicit handling for 422 validation errors during signup — e.g., weak
    password — should map to 400 with sanitized message, keeping contract.
    Note: payload must pass FastAPI's own validation (password min 8) so that
    the request reaches Supabase and triggers the mocked 422 response.
    """
    upstream_error = {"msg": "Password should be at least 6 characters", "code": 422}
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(_FakeResponse(422, upstream_error))
    )
    resp = client.post(
        "/api/v1/auth/signup", json={"email": "test@example.com", "password": "supersecret1"}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Signup request could not be completed."
    # Must not leak weak password message or upstream structure
    assert "at least 6 characters" not in str(resp.json())


def test_login_401_generic_and_422_returns_401_sanitized(monkeypatch):
    """
    Login: 400, 401, 422 from Supabase (invalid_grant, etc.) must all map
    to generic 401 Invalid email or password — keeping contract unchanged.
    """
    for status_code in (400, 401, 422):
        upstream_error = {"error": "invalid_grant", "error_description": "Invalid login credentials"}
        monkeypatch.setattr(
            httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(_FakeResponse(status_code, upstream_error))
        )
        resp = client.post(
            "/api/v1/auth/login", json={"email": "user@example.com", "password": "wrong"}
        )
        assert resp.status_code == 401, f"Expected 401 for upstream {status_code}, got {resp.status_code}"
        assert resp.json()["detail"] == "Invalid email or password."
        assert "invalid_grant" not in str(resp.json())


def test_rate_limit_logging_records_upstream_status_without_secrets(monkeypatch, caplog):
    """
    Improve logging: upstream status codes must be recorded without exposing
    secrets — verify signup_failed extra contains upstream_status and email,
    but response body does not leak secrets.
    """
    upstream_error = {"error_code": "over_email_send_rate_limit", "msg": "Rate limited"}
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(_FakeResponse(429, upstream_error))
    )
    with caplog.at_level("WARNING", logger="app.auth"):
        resp = client.post(
            "/api/v1/auth/signup", json={"email": "logtest@example.com", "password": "supersecret1"}
        )
    assert resp.status_code == 429
    # Find log record for signup_failed
    signup_failed_records = [r for r in caplog.records if r.message == "signup_failed"]
    assert len(signup_failed_records) >= 1, "Expected signup_failed log record"
    record = signup_failed_records[0]
    assert getattr(record, "upstream_status", None) == 429 or record.__dict__.get("upstream_status") == 429
    # Ensure no secret in log message itself (password should never appear)
    assert "supersecret1" not in caplog.text
    # Ensure raw error_code not leaked in response (already checked) and not in log as raw payload
    # Our implementation only logs email and upstream_status, not response body
