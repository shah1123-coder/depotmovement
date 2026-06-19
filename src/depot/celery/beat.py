"""Celery Beat schedule: periodically poll the Mail DB for new pending emails."""

from __future__ import annotations

from celery.schedules import crontab

from .app import celery_app

celery_app.conf.beat_schedule = {
    "poll-mail-db": {
        "task": "depot.discover",
        "schedule": crontab(minute="*/5"),
        "kwargs": {"insert": True},
    },
}
