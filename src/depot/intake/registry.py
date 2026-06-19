"""Fan every pending message id + attachment into a flat list of Jobs."""

from __future__ import annotations

from ..context import RunContext
from ..logging import get_logger
from ..models import Job
from ..regions.loader import get_region
from . import attachments, mail_db

log = get_logger("intake.registry")


def build_jobs(ctx: RunContext) -> list[Job]:
    # Use India's email regex as the generic sender-email matcher.
    email_rx = get_region("india").rx_email
    jobs: list[Job] = []

    for message_id in mail_db.get_pending_message_ids():
        try:
            body = mail_db.get_body_preview(message_id)
            domain = mail_db.get_sender_domain(body, email_rx)
            depot = mail_db.map_sender_to_depot(domain)
            port_id = depot[0] if depot else None

            raw = attachments.fetch_attachments(message_id)
        except Exception as exc:  # never let one message kill the batch
            log.error("intake_failed", message_id=message_id, error=str(exc))
            continue

        counter = 0
        for att in raw:
            name = att.get("name") or att.get("fileName") or ""
            if not attachments.filter_attachment(name):
                continue
            content = att.get("contentBytes") or att.get("content") or ""
            counter += 1
            saved = attachments.save_attachment(ctx, port_id, name, content, counter)
            if saved is None:
                continue
            sidecar = saved.with_suffix(saved.suffix + ".message-id")
            sidecar.write_text(message_id, encoding="utf-8")
            jobs.append(Job(file_path=str(saved), message_id=message_id, port_id=port_id))

    log.info("jobs_built", count=len(jobs))
    return jobs
