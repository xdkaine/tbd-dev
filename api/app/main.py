"""TBD Platform - Control Plane API.

FastAPI application entry point. Wires up all routers, middleware,
and lifecycle events.
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import settings
from app.database import engine
from app.middleware.rate_limit import RateLimitMiddleware
from app.models.base import Base
from app.routers import (
    admin,
    audit,
    auth,
    builds,
    deploys,
    environments,
    github,
    members,
    network_policies,
    networks,
    projects,
    quotas,
    secrets,
    templates,
    users,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler - runs on startup and shutdown."""
    logger.info("TBD Platform API starting up...")

    # --- Security: reject known-insecure secret keys ---
    _INSECURE_KEYS = {"change-me-in-production", "secret", "changeme", ""}
    if settings.secret_key in _INSECURE_KEYS:
        logger.critical(
            "FATAL: secret_key is set to an insecure default (%r). "
            "Set a strong SECRET_KEY environment variable before starting the API.",
            settings.secret_key,
        )
        sys.exit(1)

    if len(settings.secret_key) < 32:
        logger.warning(
            "secret_key is shorter than 32 characters — consider using a stronger key"
        )

    # Create tables if they don't exist (for development)
    # In production, use Alembic migrations instead
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database tables initialized")

    # Start background lifecycle service (expires_at enforcement)
    from app.services.lifecycle import run_lifecycle_loop

    lifecycle_task = asyncio.create_task(run_lifecycle_loop())

    # Start background reconciler (stale configs, duplicate IPs, stuck deploys)
    from app.services.reconciler import run_reconciler_loop

    reconciler_task = asyncio.create_task(run_reconciler_loop())

    yield

    # Shutdown: cancel background tasks
    for task in (lifecycle_task, reconciler_task):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    logger.info("TBD Platform API shutting down...")
    await engine.dispose()


app = FastAPI(
    title="TBD Platform API",
    description=(
        "Control Plane API for the TBD Platform. "
        "Manages projects, environments, builds, deploys, secrets, "
        "and network allocation for LXC-based deployments on Proxmox."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting middleware (must be added after CORS so CORS headers are present on 429s)
app.add_middleware(RateLimitMiddleware)

# Prometheus metrics — exposes GET /metrics
Instrumentator().instrument(app).expose(app)


# --- Global exception handler ---
# Catches unhandled exceptions so clients get a clean JSON 500 instead
# of a raw traceback (which may leak internal details).


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )

# --- Register Routers ---

# Auth
app.include_router(auth.router)

# Core resources
app.include_router(projects.router)
app.include_router(members.router)
app.include_router(environments.router)
app.include_router(builds.router)
app.include_router(deploys.router)
app.include_router(secrets.router)

# Infrastructure
app.include_router(networks.router)

# Integrations
app.include_router(github.router)
app.include_router(github.repo_router)

# Templates
app.include_router(templates.router)

# Admin
app.include_router(admin.router)
app.include_router(quotas.router)
app.include_router(users.router)
app.include_router(network_policies.router)

# Audit
app.include_router(audit.router)


# --- Health Check ---


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "tbd-api", "version": "0.1.0"}


@app.get("/", tags=["health"])
async def root():
    """Root endpoint - API info."""
    return {
        "service": "TBD Platform API",
        "version": "0.1.0",
        "docs": "/docs",
    }
