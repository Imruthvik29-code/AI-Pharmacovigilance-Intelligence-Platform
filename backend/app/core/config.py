"""
Application configuration.

Loads settings from environment variables (.env locally, real env vars in
deployment). Never hardcode secrets here -- see .env.example for the
expected keys.

Phase 2 addition: `http_timeout_seconds` was added so outbound HTTP calls
(e.g. to Supabase Auth) have a configurable timeout instead of a literal
hardcoded in the calling code.

Auth-fix addition (JWKS migration): `supabase_jwks_url` is a *derived*
property, not a separate env var -- Supabase Auth signs access tokens
asymmetrically (confirmed ES256 for this project) and publishes the
corresponding public keys at a fixed, well-known path under the
project's own Supabase URL. There is therefore nothing new to configure;
`SUPABASE_URL` alone is sufficient.

`supabase_jwt_secret` is DEPRECATED as of this fix -- JWT verification
now uses JWKS (see app/core/security.py) instead of the legacy HS256
shared-secret scheme, so this field is no longer read by any
verification code path. It is kept (rather than removed) purely for
backward compatibility with existing `.env` files that still set it --
removing the field outright would otherwise be a breaking config change
for any deployment that hasn't updated its `.env` yet. Safe to leave
set or to omit; either way it is now inert.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
class Settings(BaseSettings):
    database_url: str
    supabase_url: str = ""
    supabase_anon_key: str = ""
    http_timeout_seconds: float = 10.0

    #: DEPRECATED -- unused since JWT verification moved to JWKS
    #: (see app/core/security.py). Retained only so existing `.env`
    #: files with this key set continue to load without error. Do not
    #: reference this field in any new code.
    supabase_jwt_secret: str = ""

    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8",)

    @property
    def supabase_jwks_url(self) -> str:
        """
        Supabase's published JWKS (JSON Web Key Set) endpoint, derived
        from `supabase_url`. Used by app/core/security.py to verify
        ES256-signed access tokens against Supabase's public keys.

        Returns an empty string if `supabase_url` is not configured --
        callers must treat that as "JWT verification unavailable" (see
        security.py's `_get_jwks_client`), the same way missing
        `supabase_url`/`supabase_anon_key` already fail closed elsewhere
        (see api/v1/auth.py's `_supabase_headers`).
        """
        if not self.supabase_url:
            return ""
        return f"{self.supabase_url}/auth/v1/.well-known/jwks.json"


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance so we don't re-parse the environment on every call."""
    return Settings()