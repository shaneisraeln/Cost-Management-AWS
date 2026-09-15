"""Public health endpoint reporting DB and Redis connectivity."""
from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine

router = APIRouter(tags=["health"])
settings = get_settings()


async def _check_db() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False


async def _check_redis() -> str:
    """Return "ok", "unavailable", or "not_configured".

    Redis is optional: it is only used by the Celery background worker. When
    REDIS_URL is unset the API still runs; we report "not_configured" and do
    not mark the service unhealthy.
    """
    if not settings.redis_url:
        return "not_configured"
    try:
        client = aioredis.from_url(settings.redis_url)
        pong = await client.ping()
        await client.aclose()
        return "ok" if pong else "unavailable"
    except Exception:  # noqa: BLE001
        return "unavailable"


@router.get("/healthz")
async def healthz() -> dict:
    """Report liveness and dependency connectivity.

    Only the database is a required dependency; Redis is optional (worker only).
    """
    db_ok = await _check_db()
    redis_state = await _check_redis()
    return {
        "service": "cloud-cost-control-backend",
        "status": "ok" if db_ok else "degraded",
        "dependencies": {"database": db_ok, "redis": redis_state},
    }
