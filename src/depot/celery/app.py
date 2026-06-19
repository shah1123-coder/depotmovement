"""Celery app: Redis broker + result backend, late acks, requeue on loss."""

from __future__ import annotations

import os

from celery import Celery

from ..settings import get_settings
from .routing import TASK_ROUTES

_settings = get_settings()
_broker = os.environ.get(_settings.celery.broker_env) or _settings.redis_url()
_backend = os.environ.get(_settings.celery.result_env) or _settings.redis_url()

celery_app = Celery("depot", broker=_broker, backend=_backend,
                    include=["depot.celery.tasks"])

celery_app.conf.update(
    worker_concurrency=_settings.batch.workbook_concurrency,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=1800,
    task_soft_time_limit=1500,
    task_routes=TASK_ROUTES,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
)
