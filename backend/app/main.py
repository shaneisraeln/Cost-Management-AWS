"""FastAPI application factory."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    attributions,
    aws_connections,
    bedrock,
    costs,
    github,
    health,
    investigation,
    me,
    remediation,
    resources,
)
from app.core.config import get_settings
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Cloud Cost Control Platform",
        version="0.1.0",
        description="Developer-first AWS cost control platform (read-only by default).",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Public health check (no auth).
    app.include_router(health.router)

    # Versioned API (auth-guarded routers).
    app.include_router(me.router, prefix=settings.api_v1_prefix)
    app.include_router(aws_connections.router, prefix=settings.api_v1_prefix)
    app.include_router(costs.router, prefix=settings.api_v1_prefix)
    app.include_router(resources.router, prefix=settings.api_v1_prefix)
    app.include_router(attributions.router, prefix=settings.api_v1_prefix)
    app.include_router(investigation.router, prefix=settings.api_v1_prefix)
    app.include_router(github.router, prefix=settings.api_v1_prefix)
    app.include_router(remediation.router, prefix=settings.api_v1_prefix)
    app.include_router(bedrock.router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
