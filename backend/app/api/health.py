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


async def _check_redis() -> bool:
    try:
        client = aioredis.from_url(settings.redis_url)
        pong = await client.ping()
        await client.aclose()
        return bool(pong)
    except Exception:  # noqa: BLE001
        return False


@router.get("/healthz")
async def healthz() -> dict:
    """Report liveness and dependency connectivity."""
    db_ok = await _check_db()
    redis_ok = await _check_redis()
    return {
        "service": "cloud-cost-control-backend",
        "status": "ok" if db_ok and redis_ok else "degraded",
        "dependencies": {"database": db_ok, "redis": redis_ok},
    }
