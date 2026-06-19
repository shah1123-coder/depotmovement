"""Three queues keep heavy parsing off the intake/IO path."""

from __future__ import annotations

TASK_ROUTES = {
    "depot.discover": {"queue": "intake"},
    "depot.process_workbook": {"queue": "process"},
    "depot.persist": {"queue": "persist"},
}
