"""
Phase 2 auth tests: JWT verification logic.

These are pure unit tests for the current JWKS-backed verification path.
No real network calls are made: the JWKS client is mocked, while JWT
signature verification still runs through PyJWT using a generated ES256
key pair.
"""
import asyncio
import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

import app.core.security as security


TEST_SUPABASE_URL = "https://example.supabase.co"


@pytest.fixture(autouse=True)
def _configure_settings(monkeypatch):
    monkeypatch.setattr(security.settings, "supabase_url", TEST_SUPABASE_URL)
    monkeypatch.setattr(security, "_jwks_client", None)


@pytest.fixture
def es256_keypair():
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    return private_key, public_key


def _make_token(private_key, sub: str, *, exp_delta: int = 3600) -> str:
    payload = {
        "sub": sub,
        "email": "user@example.com",
        "aud": "authenticated",
        "iss": f"{TEST_SUPABASE_URL}/auth/v1",
        "exp": int(time.time()) + exp_delta,
    }
    return jwt.encode(payload, private_key, algorithm="ES256", headers={"kid": "test-kid"})


def _patch_jwks_client(monkeypatch, public_key):
    class _FakeJwksClient:
        def get_signing_key_from_jwt(self, token: str):
            class _SigningKey:
                key = public_key

            return _SigningKey()

    monkeypatch.setattr(security, "_get_jwks_client", lambda: _FakeJwksClient())


def test_decode_valid_token(monkeypatch, es256_keypair):
    private_key, public_key = es256_keypair
    token = _make_token(private_key, str(uuid.uuid4()))
    _patch_jwks_client(monkeypatch, public_key)

    payload = security.decode_supabase_jwt(token)
    assert payload["aud"] == "authenticated"
    assert payload["iss"] == f"{TEST_SUPABASE_URL}/auth/v1"


def test_decode_expired_token_raises_401(monkeypatch, es256_keypair):
    private_key, public_key = es256_keypair
    token = _make_token(private_key, str(uuid.uuid4()), exp_delta=-10)
    _patch_jwks_client(monkeypatch, public_key)

    with pytest.raises(HTTPException) as exc_info:
        security.decode_supabase_jwt(token)
    assert exc_info.value.status_code == 401


def test_decode_unknown_kid_raises_401(monkeypatch):
    class _FakeJwksClient:
        def get_signing_key_from_jwt(self, token: str):
            raise security.PyJWKClientError("Unable to find a signing key")

    monkeypatch.setattr(security, "_get_jwks_client", lambda: _FakeJwksClient())

    with pytest.raises(HTTPException) as exc_info:
        security.decode_supabase_jwt("irrelevant")
    assert exc_info.value.status_code == 401


def test_decode_missing_config_raises_500(monkeypatch):
    monkeypatch.setattr(security.settings, "supabase_url", "")
    monkeypatch.setattr(security, "_jwks_client", None)

    with pytest.raises(HTTPException) as exc_info:
        security.decode_supabase_jwt("irrelevant")
    assert exc_info.value.status_code == 500


def test_get_current_user_rejects_malformed_sub(monkeypatch):
    monkeypatch.setattr(security, "decode_supabase_jwt", lambda token: {"sub": "not-a-uuid"})

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(security.get_current_user(credentials))
    assert exc_info.value.status_code == 401
