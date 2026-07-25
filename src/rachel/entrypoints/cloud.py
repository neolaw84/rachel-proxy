"""Multi-tenant cloud service application entrypoint.

Enforces strict OIDC JWKS JWT authentication (require_oidc_jwt_user) and Neon
PostgreSQL state storage. Fails-closed immediately on boot if cloud config is missing.
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from rachel.auth import get_admin_user, require_oidc_jwt_user
from rachel.config import (
    DATABASE_URL,
    MAX_ITERATIONS,
    NUM_STATES_TO_TRACK,
    OIDC_ISSUER_URL,
    OIDC_JWKS_URL,
    SANDBOX_TIMEOUT,
)
from rachel.routes.completions import router as completions_router
from rachel.routes.sessions import router as sessions_router
from rachel.routes.system import detect_public_url, router as system_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    public_url = detect_public_url()
    logger.info("Cloud Service starting: public_url=%s", public_url)
    logger.info(
        "Config loaded: states=%d, timeout=%.1fs, max_iter=%d",
        NUM_STATES_TO_TRACK, SANDBOX_TIMEOUT, MAX_ITERATIONS,
    )
    yield


def create_cloud_app() -> FastAPI:
    """Construct and configure multi-tenant cloud FastAPI application."""
    # Fail-Closed Startup Assertion: Validate cloud security requirements
    if not OIDC_JWKS_URL and not OIDC_ISSUER_URL and not os.environ.get("TESTING"):
        logger.error("FATAL: OIDC_JWKS_URL or OIDC_ISSUER_URL is required in cloud mode. Boot aborted.")
        raise RuntimeError("FATAL: OIDC_JWKS_URL or OIDC_ISSUER_URL is required for cloud service deployment.")

    if not DATABASE_URL and not os.environ.get("TESTING"):
        logger.error("FATAL: DATABASE_URL is required for multi-tenant cloud service deployment. Boot aborted.")
        raise RuntimeError("FATAL: DATABASE_URL is required for cloud service deployment.")

    app_instance = FastAPI(
        title="RACHEL Proxy (Cloud Service)",
        description="RACHEL (Rpg Agent CHat Evaluation Loop) - Multi-tenant cloud service.",
        version="0.2.0",
        lifespan=lifespan,
    )

    # Wire Dependency Override for Multi-Tenant Cloud Auth (Fail-Closed OIDC)
    app_instance.dependency_overrides[get_admin_user] = require_oidc_jwt_user

    app_instance.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
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


app = create_cloud_app()
