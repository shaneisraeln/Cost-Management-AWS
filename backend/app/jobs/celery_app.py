"""Celery application (Redis broker + result backend).

Periodic sync jobs (cost, resource, cloudtrail, metrics, aggregation,
anomaly detection) are registered on the Beat schedule in later phases.
"""
from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "cloud_cost_control",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    timezone="UTC",
)

# Discover task modules.
celery_app.autodiscover_tasks(["app.jobs"])
import app.jobs.tasks  # noqa: E402,F401 - ensure tasks register on import


@celery_app.task(name="smoke.ping")
def ping() -> str:
    """Smoke task used to verify the worker is running."""
    return "pong"
