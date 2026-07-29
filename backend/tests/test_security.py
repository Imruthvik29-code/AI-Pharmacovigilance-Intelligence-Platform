"""
Phase 2 auth tests: JWT verification logic.

Pure unit tests -- no network or live Supabase instance required, since
decode_supabase_jwt only needs the shared HMAC secret to verify a token's
signature/claims. Contrast with Phase 1's test_database.py, which needs a
live DB.
"""
import time
import uuid

import jwt
import pytest
from fastapi import HTTPException

from app.core.config import get_settings
from app.core.security import decode_supabase_jwt

settings = get_settings()
TEST_SECRET = "test-secret-for-unit-tests-only"


def _make_token(sub: str, exp_delta: int = 3600, secret: str = TEST_SECRET) -> str:
    payload = {
        "sub": sub,
        "email": "user@example.com",
        "aud": "authenticated",
        "exp": int(time.time()) + exp_delta,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture(autouse=True)
def _configure_secret(monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", TEST_SECRET)


def test_decode_valid_token():
    user_id = str(uuid.uuid4())
    token = _make_token(user_id)
    payload = decode_supabase_jwt(token)
    assert payload["sub"] == user_id
    assert payload["aud"] == "authenticated"


def test_decode_expired_token_raises_401():
    token = _make_token(str(uuid.uuid4()), exp_delta=-10)
    with pytest.raises(HTTPException) as exc_info:
        decode_supabase_jwt(token)
    assert exc_info.value.status_code == 401


def test_decode_token_wrong_secret_raises_401():
    token = _make_token(str(uuid.uuid4()), secret="a-completely-different-secret")
    with pytest.raises(HTTPException) as exc_info:
        decode_supabase_jwt(token)
    assert exc_info.value.status_code == 401


def test_decode_missing_secret_raises_500(monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", "")
    with pytest.raises(HTTPException) as exc_info:
        decode_supabase_jwt("irrelevant")
    assert exc_info.value.status_code == 500
