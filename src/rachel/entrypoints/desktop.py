"""Single-tenant standalone desktop application entrypoint.

Wires local admin authentication (require_local_admin_key) and serves
desktop static assets from src/rachel/static. Zero cloud SSO dependencies.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from rachel.auth import PROXY_API_KEY, get_admin_user, require_local_admin_key
from rachel.config import MAX_ITERATIONS, NUM_STATES_TO_TRACK, SANDBOX_TIMEOUT
from rachel.routes.completions import router as completions_router
from rachel.routes.sessions import router as sessions_router
from rachel.routes.system import detect_public_url, router as system_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    public_url = detect_public_url()
    api_endpoint = f"{public_url}/v1"
    dashboard_url = f"{public_url}/"
    print(
        "\n" + "=" * 60 + "\n"
        f"  Proxy API Key (use as Bearer token):\n"
        f"  {PROXY_API_KEY}\n"
        "\n"
        f"  Server Public URL:  {public_url}\n"
        f"  Proxy API Endpoint: {api_endpoint}\n"
        f"  Dashboard URL:      {dashboard_url}\n"
        + "=" * 60 + "\n"
    )
    logger.info(
        "Config loaded: states=%d, timeout=%.1fs, max_iter=%d",
        NUM_STATES_TO_TRACK, SANDBOX_TIMEOUT, MAX_ITERATIONS,
    )
    logger.info("Server Public URL:  %s", public_url)
    logger.info("Proxy API Endpoint: %s", api_endpoint)
    logger.info("Dashboard URL:      %s", dashboard_url)
    yield


def create_desktop_app() -> FastAPI:
    """Construct and configure single-tenant desktop FastAPI application."""
    app_instance = FastAPI(
        title="RACHEL Proxy (Desktop)",
        description="RACHEL (Rpg Agent CHat Evaluation Loop) - Single-tenant desktop application.",
        version="0.2.0",
        lifespan=lifespan,
    )

    # Wire Dependency Override for Single-Tenant Desktop Auth
    app_instance.dependency_overrides[get_admin_user] = require_local_admin_key

    app_instance.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://janitorai.com",
            "https://app.wyvern.chat",
            "https://app.wyvern.chat/sim",
            "https://wyvern.chat",
        ],
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    assets_dir = os.path.join(static_dir, "assets")

    if os.path.exists(assets_dir):
        app_instance.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    if os.path.exists(static_dir):
        app_instance.mount("/static", StaticFiles(directory=static_dir), name="static")

    app_instance.include_router(completions_router)
    app_instance.include_router(sessions_router)
    app_instance.include_router(system_router)

    return app_instance


app = create_desktop_app()
