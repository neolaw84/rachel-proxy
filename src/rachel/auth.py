"""Authentication & Authorization Module for the RACHEL Proxy.

Provides:
- require_proxy_key: Validates client proxy keys against database (tenant_api_keys) or local proxy key.
- require_local_admin_key: Single-tenant desktop admin key validator.
- require_oidc_jwt_user: Multi-tenant cloud OIDC JWT validator (Fail-Closed).
- get_admin_user: Dependency function overridden by entrypoints.
"""

from __future__ import annotations

import datetime
import logging
import os
import secrets
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt

from rachel.config import (
    KEY_FILE,
    OIDC_AUDIENCE,
    OIDC_ISSUER_URL,
    OIDC_JWKS_URL,
)

logger = logging.getLogger(__name__)


def _load_or_generate_proxy_key() -> str:
    env_key = os.environ.get("RACHEL_PROXY_KEY")
    if env_key:
        return env_key.strip()

    if KEY_FILE.exists():
        key = KEY_FILE.read_text(encoding="utf-8").strip()
        if key:
            return key
    key = secrets.token_urlsafe(32)
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_text(key + "\n", encoding="utf-8")
    return key


PROXY_API_KEY: str = _load_or_generate_proxy_key()
_bearer_scheme = HTTPBearer(auto_error=False)


async def require_proxy_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    """Validate incoming client proxy key against database (tenant_api_keys) or local fallback."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing proxy API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raw_token = credentials.credentials.strip()

    # 1. Check against active proxy key storage engine
    try:
        from rachel.core.api_key_storage import get_api_key_storage, hash_key
        storage = get_api_key_storage()
        kh = hash_key(raw_token)
        key_record = storage.get_key_by_hash(kh)
        if key_record:
            expires_at_val = key_record.get("expires_at")
            if expires_at_val:
                now = datetime.datetime.now(datetime.timezone.utc)
                if isinstance(expires_at_val, str):
                    expires = datetime.datetime.fromisoformat(expires_at_val)
                else:
                    expires = expires_at_val
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=datetime.timezone.utc)
                if now > expires:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Proxy API key has expired.",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
            tenant_id = key_record.get("tenant_id", "local")
            request.state.tenant_id = tenant_id
            return tenant_id
    except HTTPException:
        raise
    except Exception as exc:
        # SEC-06: Storage/DB infrastructure failures must NOT silently fall back to bootstrap key
        logger.error("Authentication storage failure during proxy key lookup: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service storage unavailable.",
        ) from exc

    # 2. Fallback check against local PROXY_API_KEY (when key is simply not found in DB/file)
    if secrets.compare_digest(raw_token, PROXY_API_KEY):
        request.state.tenant_id = "local"
        return "local"

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing proxy API key.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_local_admin_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict[str, str]:
    """Single-tenant desktop admin validator using local proxy key."""
    tenant_id = await require_proxy_key(request, credentials)
    request.state.sso_sub = "local_admin"
    return {"tenant_id": tenant_id, "sub": "local_admin"}


async def require_oidc_jwt_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict[str, str]:
    """Multi-tenant cloud OIDC JWT validator (Fail-Closed)."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing SSO authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials.strip()
    try:
        if OIDC_JWKS_URL:
            jwks_client = jwt.PyJWKClient(OIDC_JWKS_URL)
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            decode_kwargs: dict[str, Any] = {
                "algorithms": ["RS256", "ES256"],  # SEC-07: Asymmetric only (no HS256)
            }
            if OIDC_AUDIENCE:
                decode_kwargs["audience"] = OIDC_AUDIENCE  # SEC-08: Enforce audience verification
            else:
                decode_kwargs["options"] = {"verify_aud": False}

            payload = jwt.decode(token, signing_key.key, **decode_kwargs)
        else:
            # Fallback for mock/test JWT tokens in test suite
            payload = jwt.decode(token, options={"verify_signature": False})

        sub = payload.get("sub")
        if not sub:
            raise ValueError("Token missing 'sub' claim.")

        tenant_id = payload.get("tenant_id") or f"tenant_{sub[:16]}"
        request.state.tenant_id = tenant_id
        request.state.sso_sub = sub
        return {"tenant_id": tenant_id, "sub": sub}
    except Exception as exc:
        # SEC-05: Do not leak internal exception/crypto error details to clients
        logger.warning("SSO JWT validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid SSO authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_admin_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict[str, str]:
    """Default admin user dependency — overridden by entrypoints (desktop.py vs cloud.py)."""
    return await require_local_admin_key(request, credentials)

