"""System Endpoints Router.

Serves the administration dashboard SPA, a favicon stub, a public health
check, status endpoint, provider configuration endpoints, and OpenRouter PKCE OAuth flow.
"""

from __future__ import annotations

import base64
import hashlib
import jwt
import os
import secrets
from typing import Any
import httpx


from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from rachel.auth import get_admin_user, require_proxy_key
from rachel.config import (
    CONFIG_PUBLIC_URL,
    MAX_ITERATIONS,
    NUM_STATES_TO_TRACK,
    SANDBOX_TIMEOUT,
    STATE_STORAGE_DIR,
    STORAGE_ENGINE,
)
from rachel.core.state import list_all_sessions
from rachel.core.settings_storage import (
    DEFAULT_PROVIDER_BASE_URLS,
    DEFAULT_PROVIDER_MODELS,
    get_settings_storage,
)

router = APIRouter(tags=["system"])

_STATIC_INDEX = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "index.html")



# ---------------------------------------------------------------------------
# Public URL detection
# ---------------------------------------------------------------------------

def detect_public_url() -> str:
    """Detect the server's externally-reachable base URL.

    Resolution order (highest priority first):
    1. ``configs.yaml`` -> ``server.public_url`` (if explicitly set)
    2. ``SPACE_HOST`` — set by Hugging Face Spaces.
    3. ``RAILWAY_PUBLIC_DOMAIN`` — set by Railway deployments.
    4. Falls back to ``http://localhost:{PORT}`` using the ``PORT`` env var (default 8000).
    """
    if CONFIG_PUBLIC_URL:
        host = str(CONFIG_PUBLIC_URL).rstrip("/")
        return f"https://{host}" if not host.startswith("http") else host

    hf_host = os.environ.get("SPACE_HOST")
    if hf_host:
        host = hf_host.rstrip("/")
        return f"https://{host}" if not host.startswith("http") else host

    railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
    if railway_domain:
        host = railway_domain.rstrip("/")
        return f"https://{host}" if not host.startswith("http") else host

    port = int(os.environ.get("PORT", 8000))
    return f"http://localhost:{port}"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard() -> HTMLResponse:
    """Serve the single-page administration dashboard."""
    try:
        with open(_STATIC_INDEX, encoding="utf-8") as fh:
            return HTMLResponse(fh.read())
    except FileNotFoundError:
        return HTMLResponse(
            "<h1>Dashboard not found</h1><p>Compiled index.html is missing. Run <code>python scripts/build_frontend.py</code>.</p>",
            status_code=500,
        )


@router.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    """Return an empty response for favicon requests to suppress 404 errors."""
    return Response(status_code=204)


@router.get("/health")
async def health() -> dict[str, str]:
    """Simple public health check endpoint."""
    return {"status": "ok"}


@router.get("/v1/status", dependencies=[Depends(get_admin_user)])
async def proxy_status(request: Request) -> dict:
    """Return configuration and runtime status for the dashboard."""
    from rachel.sandbox.sandbox import get_sandbox_engine
    tenant_id = getattr(request.state, "tenant_id", "local")
    public_url = detect_public_url()
    storage = get_settings_storage(tenant_id=tenant_id)
    active_provider, _, api_key, _ = storage.get_active_provider_details()
    return {
        "active_provider": active_provider,
        "provider_key_set": bool(api_key),
        "openrouter_key_set": bool(api_key),  # Backward compatibility
        "sandbox_engine": get_sandbox_engine().name,
        "storage_engine": STORAGE_ENGINE,
        "state_storage_dir": str(STATE_STORAGE_DIR),
        "num_states_to_track": NUM_STATES_TO_TRACK,
        "sandbox_timeout": SANDBOX_TIMEOUT,
        "max_iterations": MAX_ITERATIONS,
        "active_sessions_count": len(list_all_sessions(tenant_id=tenant_id)),
        "public_url": public_url,
        "api_endpoint": f"{public_url}/v1",
    }


# ---------------------------------------------------------------------------
# Provider & Credentials Management Endpoints
# ---------------------------------------------------------------------------

@router.get("/v1/providers", dependencies=[Depends(get_admin_user)])
async def list_providers(request: Request) -> dict[str, Any]:
    """Return configured active provider and credential status map."""
    tenant_id = getattr(request.state, "tenant_id", "local")
    storage = get_settings_storage(tenant_id=tenant_id)
    active_provider = storage.get_active_provider()
    creds = storage.get_credentials()
    localhost_key_not_needed = storage.get_localhost_key_not_needed()
    localhost_base_url = storage.get_localhost_base_url()

    provider_status = {}
    for p in DEFAULT_PROVIDER_BASE_URLS.keys():
        key = creds.get(p, "")
        is_configured = bool(key)
        if p == "localhost_byok" and localhost_key_not_needed:
            is_configured = True
        base_url = DEFAULT_PROVIDER_BASE_URLS[p]
        if p == "localhost_byok" and localhost_base_url:
            base_url = localhost_base_url
        provider_status[p] = {
            "configured": is_configured,
            "base_url": base_url,
            "default_model": DEFAULT_PROVIDER_MODELS[p],
        }

    return {
        "active_provider": active_provider,
        "providers": provider_status,
        "localhost_key_not_needed": localhost_key_not_needed,
        "localhost_base_url": localhost_base_url,
    }


@router.post("/v1/providers/active", dependencies=[Depends(get_admin_user)])
async def set_active_provider(payload: dict[str, Any], request: Request) -> dict[str, str]:
    """Set active provider in SettingsStorage."""
    provider = payload.get("provider")
    if not provider or provider not in DEFAULT_PROVIDER_BASE_URLS:
        raise HTTPException(status_code=400, detail=f"Invalid provider: '{provider}'")
    tenant_id = getattr(request.state, "tenant_id", "local")
    storage = get_settings_storage(tenant_id=tenant_id)
    storage.set_active_provider(provider)
    return {"status": "ok", "active_provider": provider}


@router.post("/v1/providers/credentials", dependencies=[Depends(get_admin_user)])
async def set_provider_credentials(payload: dict[str, Any], request: Request) -> dict[str, str]:
    """Save secret API key for specified provider into SettingsStorage."""
    provider = payload.get("provider")
    api_key = payload.get("api_key")
    if not provider or provider not in DEFAULT_PROVIDER_BASE_URLS:
        raise HTTPException(status_code=400, detail=f"Invalid provider: '{provider}'")
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required.")

    tenant_id = getattr(request.state, "tenant_id", "local")
    storage = get_settings_storage(tenant_id=tenant_id)
    storage.set_credential(provider, api_key)
    return {"status": "ok", "provider": provider}


@router.post("/v1/providers/localhost-key-not-needed", dependencies=[Depends(get_admin_user)])
async def set_localhost_key_not_needed(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Toggle whether an API key is needed for localhost_byok provider."""
    enabled = payload.get("enabled")
    if enabled is None:
        raise HTTPException(status_code=400, detail="Field 'enabled' (boolean) is required.")
    tenant_id = getattr(request.state, "tenant_id", "local")
    storage = get_settings_storage(tenant_id=tenant_id)
    storage.set_localhost_key_not_needed(bool(enabled))
    return {"status": "ok", "localhost_key_not_needed": bool(enabled)}


@router.post("/v1/providers/localhost-base-url", dependencies=[Depends(get_admin_user)])
async def set_localhost_base_url(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Set custom base URL for localhost_byok provider."""
    raw_url = payload.get("base_url")
    if raw_url is not None:
        url_str = str(raw_url).strip()
        if url_str and not (url_str.startswith("http://") or url_str.startswith("https://")):
            raise HTTPException(status_code=400, detail="Base URL must start with http:// or https://")
        new_url = url_str if url_str else None
    else:
        new_url = None

    tenant_id = getattr(request.state, "tenant_id", "local")
    storage = get_settings_storage(tenant_id=tenant_id)
    storage.set_localhost_base_url(new_url)
    return {"status": "ok", "localhost_base_url": new_url}


# ---------------------------------------------------------------------------
# Client Proxy Key Management Endpoints
# ---------------------------------------------------------------------------

@router.post("/v1/proxy-keys", dependencies=[Depends(get_admin_user)])
async def create_proxy_key(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Generate a new client proxy key (sk-local-... or sk-tenant-...)."""
    from datetime import datetime, timezone, timedelta
    from rachel.core.api_key_storage import get_api_key_storage

    name = str(payload.get("name", "Default Proxy Key")).strip()
    expires_in_days = payload.get("expires_in_days")
    tenant_id = getattr(request.state, "tenant_id", "local")

    prefix = "sk-local-" if tenant_id == "local" else "sk-tenant-"
    raw_key = f"{prefix}{secrets.token_hex(20)}"

    expires_at = None
    if expires_in_days is not None:
        try:
            expires_at = datetime.now(timezone.utc) + timedelta(days=int(expires_in_days))
        except (ValueError, TypeError):
            pass

    storage = get_api_key_storage(tenant_id=tenant_id)
    record = storage.create_key(
        name=name,
        prefix=prefix,
        raw_key=raw_key,
        expires_at=expires_at,
    )

    return {
        "id": record["id"],
        "tenant_id": tenant_id,
        "name": name,
        "prefix": prefix,
        "proxy_key": raw_key,
        "expires_at": expires_at.isoformat() if expires_at else None,
    }


@router.get("/v1/proxy-keys", dependencies=[Depends(get_admin_user)])
async def list_proxy_keys(request: Request) -> dict[str, Any]:
    """List proxy keys for the active tenant."""
    from rachel.core.api_key_storage import get_api_key_storage
    tenant_id = getattr(request.state, "tenant_id", "local")

    storage = get_api_key_storage(tenant_id=tenant_id)
    keys_list = storage.list_keys()
    return {"keys": keys_list, "count": len(keys_list)}


@router.delete("/v1/proxy-keys/{key_id}", dependencies=[Depends(get_admin_user)])
async def revoke_proxy_key(key_id: str, request: Request) -> dict[str, str]:
    """Revoke (deactivate) a client proxy key."""
    from rachel.core.api_key_storage import get_api_key_storage
    tenant_id = getattr(request.state, "tenant_id", "local")

    storage = get_api_key_storage(tenant_id=tenant_id)
    success = storage.revoke_key(key_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Proxy key '{key_id}' not found.")
    return {"status": "ok", "message": f"Proxy key '{key_id}' revoked."}


# ---------------------------------------------------------------------------
# OpenRouter OAuth PKCE Flow
# ---------------------------------------------------------------------------
# PKCE OpenRouter OAuth Flow (Stateless, HMAC-signed JWT state tokens)
# ---------------------------------------------------------------------------

@router.get("/v1/auth/openrouter/authorize")
async def openrouter_authorize(
    request: Request,
    tenant_id: str = Query("local"),
) -> RedirectResponse:
    """Initiate OpenRouter PKCE OAuth flow with a self-contained signed state token."""
    import time
    from rachel.auth import PROXY_API_KEY

    # 1. Generate PKCE verifier (43-128 chars base64url)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("utf-8")).digest()
    ).decode("utf-8").rstrip("=")

    # 2. Create HMAC-SHA256 signed JWT state token encoding verifier + tenant_id (10-min exp)
    state_payload = {
        "cv": code_verifier,
        "tid": tenant_id,
        "exp": int(time.time()) + 600,
        "aud": "pkce",
    }
    state_token = jwt.encode(state_payload, PROXY_API_KEY, algorithm="HS256")

    public_url = detect_public_url()
    callback_url = f"{public_url}/v1/auth/openrouter/callback"

    auth_url = (
        f"https://openrouter.ai/auth"
        f"?callback_url={callback_url}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
        f"&state={state_token}"
    )
    return RedirectResponse(auth_url)


@router.get("/v1/auth/openrouter/callback")
async def openrouter_callback(
    code: str = Query(...),
    state: str | None = Query(None),
) -> HTMLResponse:
    """Handle OpenRouter OAuth PKCE callback and exchange code for API key."""
    from rachel.auth import PROXY_API_KEY

    if not state:
        raise HTTPException(status_code=400, detail="Missing OAuth state parameter.")

    # 1. Verify and decode HMAC-signed state token
    try:
        payload = jwt.decode(state, PROXY_API_KEY, algorithms=["HS256"], audience="pkce")
        code_verifier = payload["cv"]
        tenant_id = payload.get("tid", "local")
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="OAuth state mismatch or session expired. Please restart the authorization flow.",
        ) from exc

    # 2. Exchange authorization code for OpenRouter API key
    token_url = "https://openrouter.ai/api/v1/auth/keys"
    req_payload = {
        "code": code,
        "code_verifier": code_verifier,
        "code_challenge_method": "S256",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(token_url, json=req_payload)
        if res.status_code >= 400:
            raise HTTPException(
                status_code=400,
                detail=f"OpenRouter key exchange failed ({res.status_code}): {res.text}",
            )
        data = res.json()
        api_key = data.get("key")
        if not api_key:
            raise HTTPException(status_code=500, detail="OpenRouter did not return an API key.")

    # 3. Save to tenant-isolated SettingsStorage
    storage = get_settings_storage(tenant_id=tenant_id)
    storage.set_credential("openrouter_pkce", api_key)
    storage.set_active_provider("openrouter_pkce")


    success_html = """
    <!DOCTYPE html>
    <html>
    <head><title>OpenRouter Authorized</title></head>
    <body style="font-family: sans-serif; background: #0b0e1a; color: #d4deff; text-align: center; padding-top: 50px;">
        <h2 style="color: #22d36e;">✓ OpenRouter Connected Successfully!</h2>
        <p>Your OpenRouter PKCE token has been saved and selected as the Active Provider.</p>
        <p><a href="/" style="color: #6c8aff; text-decoration: underline;">Return to Admin Dashboard</a></p>
        <script>setTimeout(function() { window.location.href = "/"; }, 2500);</script>
    </body>
    </html>
    """
    return HTMLResponse(content=success_html)
