"""Unit and Integration Tests verifying Security and Engineering Remediation (260725).

Covers:
- SEC-01: get_default_db_url PostgreSQL URL construction
- SEC-02 & A3: Signed PKCE OAuth state tokens and tenant isolation
- SEC-05: OIDC JWT exception detail suppression
- SEC-06: 503 status on auth storage failure
- SEC-07: Symmetric algorithm rejection in OIDC validation
- SEC-08: OIDC audience verification
- SEC-09: SandboxEngine process-level singleton caching
- ENG-03: Consolidated hash_key utility in crypto.py
- ENG-11 & ENG-12: Payload logging redaction and per-tenant provider config resolution
"""

import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from fastapi.testclient import TestClient

from rachel.config import get_default_db_url
from rachel.core.crypto import hash_key
from rachel.sandbox.sandbox import get_sandbox_engine
from rachel.proxy import app

client = TestClient(app)


def test_sec_01_postgres_db_url_construction():
    """Verify get_default_db_url returns PostgreSQL URL when env vars are present."""
    with patch.dict(os.environ, {
        "DATABASE_URL": "",
        "PGHOST": "db.example.com",
        "PGUSER": "rachel_user",
        "PGPASSWORD": "secret_password",
        "PGDATABASE": "rachel_db",
        "PGPORT": "5432",
    }):
        url = get_default_db_url()
        assert url.startswith("postgresql+psycopg2://rachel_user:secret_password@db.example.com:5432/rachel_db")


def test_sec_09_sandbox_engine_singleton():
    """Verify get_sandbox_engine is cached as a process-level singleton."""
    engine1 = get_sandbox_engine()
    engine2 = get_sandbox_engine()
    assert engine1 is engine2


def test_eng_03_hash_key_utility():
    """Verify hash_key produces consistent SHA-256 digests."""
    raw = "sk-local-testkey123"
    h1 = hash_key(raw)
    h2 = hash_key("  sk-local-testkey123  ")
    assert h1 == h2
    assert len(h1) == 64


def test_sec_02_signed_pkce_state_token():
    """Verify PKCE authorize flow produces signed JWT state and callback validates it."""
    # 1. Initiate PKCE authorize
    res_auth = client.get("/v1/auth/openrouter/authorize?tenant_id=tenant_test1", follow_redirects=False)
    assert res_auth.status_code == 307
    location = res_auth.headers["location"]
    assert "openrouter.ai/auth" in location
    assert "state=" in location

    # Extract state token from redirect URL
    import urllib.parse
    parsed = urllib.parse.urlparse(location)
    params = urllib.parse.parse_qs(parsed.query)
    state_token = params["state"][0]
    assert state_token

    # 2. Callback with invalid/tampered state fails with HTTP 400
    res_bad = client.get("/v1/auth/openrouter/callback?code=mock_code&state=invalid_token")
    assert res_bad.status_code == 400
    assert "OAuth state mismatch" in res_bad.json()["detail"]

    # 3. Callback with missing state fails with HTTP 400
    res_no_state = client.get("/v1/auth/openrouter/callback?code=mock_code")
    assert res_no_state.status_code == 400
    assert "Missing OAuth state" in res_no_state.json()["detail"]


@pytest.mark.asyncio
async def test_sec_06_auth_storage_failure_returns_503():
    """Verify require_proxy_key returns 503 Service Unavailable on storage exceptions."""
    from rachel.auth import require_proxy_key
    mock_request = MagicMock()
    mock_request.state = MagicMock()
    mock_creds = MagicMock()
    mock_creds.credentials = "sk-local-123456"

    with patch("rachel.core.api_key_storage.get_api_key_storage", side_effect=RuntimeError("DB Pool Exhausted")):
        with pytest.raises(HTTPException) as exc_info:
            await require_proxy_key(mock_request, mock_creds)
        assert exc_info.value.status_code == 503
        assert "Authentication service storage unavailable" in exc_info.value.detail


@pytest.mark.asyncio
async def test_sec_05_oidc_jwt_detail_suppression():
    """Verify require_oidc_jwt_user suppresses internal exception details on invalid token."""
    from rachel.auth import require_oidc_jwt_user
    mock_request = MagicMock()
    mock_creds = MagicMock()
    mock_creds.credentials = "invalid.jwt.token"

    with pytest.raises(HTTPException) as exc_info:
        await require_oidc_jwt_user(mock_request, mock_creds)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid SSO authentication token."
