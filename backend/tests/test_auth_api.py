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
