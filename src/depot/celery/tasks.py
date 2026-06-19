"""Celery tasks: discover -> fan-out per workbook -> chord -> persist once."""

from __future__ import annotations

from celery import chord

from ..context import RunContext
from ..db import persist
from ..db.batcher import build_cache
from ..intake import mail_db, registry
from ..logging import bind, get_logger
from ..models import GateInRecord, GateOutRecord
from ..output import json_writer
from ..pipeline import extract_workbook
from ..settings import get_settings
from ..validate.gate_in import validate_gate_in
from ..validate.gate_out import validate_gate_out
from .app import celery_app

log = get_logger("celery.tasks")


@celery_app.task(name="depot.discover")
def discover_task(insert: bool = False) -> dict:
    settings = get_settings()
    ctx = RunContext.create(settings)
    bind(run_id=ctx.run_id)
    jobs = registry.build_jobs(ctx)
    if not jobs:
        log.info("no_jobs", run_id=ctx.run_id)
        ctx.publish()
        return {"run_id": ctx.run_id, "jobs": 0}

    header = [process_workbook_task.s(job.model_dump()) for job in jobs]
    callback = persist_task.s(run_id=ctx.run_id, run_dir=str(ctx.run_dir),
                              final_dir=str(ctx.final_run_dir), insert=insert)
    chord(header)(callback)
    return {"run_id": ctx.run_id, "jobs": len(jobs)}


@celery_app.task(name="depot.process_workbook", bind=True)
def process_workbook_task(self, job: dict) -> dict:
    extraction = extract_workbook(job["file_path"], job.get("message_id", ""))
    return {
        "file": extraction.file,
        "message_id": extraction.message_id,
        "region": extraction.region,
        "skipped": extraction.skipped,
        "in_records": [r.model_dump() for r in extraction.in_records],
        "out_records": [r.model_dump() for r in extraction.out_records],
        "failures": extraction.failures,
    }


@celery_app.task(name="depot.persist")
def persist_task(results: list[dict], run_id: str, run_dir: str,
                 final_dir: str, insert: bool = False) -> dict:
    bind(run_id=run_id)
    from pathlib import Path

    # Re-hydrate extraction records.
    all_in = [GateInRecord(**r) for res in results for r in res["in_records"]]
    all_out = [GateOutRecord(**r) for res in results for r in res["out_records"]]

    cache = build_cache(all_in, all_out)

    final_in, final_out, error_rows = [], [], []
    message_ids = set()
    for res in results:
        if res.get("message_id"):
            message_ids.add(res["message_id"])
        plot_id = persist.plot_id_from_filename(res["file"])
        in_recs = [GateInRecord(**r) for r in res["in_records"]]
        out_recs = [GateOutRecord(**r) for r in res["out_records"]]
        v_in = validate_gate_in(in_recs, cache, plot_id)
        v_out = validate_gate_out(out_recs, cache, plot_id)
        final_in.extend(v_in)
        final_out.extend(v_out)

    counts = json_writer.write_outputs(Path(run_dir), final_in, final_out)

    db_counts = {}
    if insert:
        db_counts["gate_in"] = persist.insert_gate_in(final_in)
        db_counts["gate_out"] = persist.insert_gate_out(final_out)
        error_rows = _error_dicts(final_in, final_out)
        db_counts["errors"] = persist.insert_errors(error_rows)
        rc = mail_db.mark_completed(list(message_ids))
        db_counts["mail_completed"] = rc

    # Atomic publish of the whole run folder.
    try:
        import os
        if Path(run_dir) != Path(final_dir):
            Path(final_dir).parent.mkdir(parents=True, exist_ok=True)
            if Path(final_dir).exists():
                import shutil
                shutil.rmtree(final_dir)
            os.replace(run_dir, final_dir)
    except Exception as exc:
        log.error("publish_failed", error=str(exc))

    log.info("run_complete", run_id=run_id, counts=counts, db_counts=db_counts)
    return {"run_id": run_id, "counts": counts, "db_counts": db_counts}


def _error_dicts(final_in, final_out) -> list[dict]:
    rows = []
    for r in final_in:
        if r.ErrorCode:
            rows.append({"GateType": "IN", "ErrorCode": r.ErrorCode,
                         "ContainerId": r.ContainerId, "PlotID": r.PlotID,
                         "PlotInDate": r.PlotInDate, "PlotInStatus": "P",
                         "CreatedBy": 1, "Remarks": r.Remarks,
                         "ContainerStatusId": r.ContainerStatusId})
    for r in final_out:
        if r.ErrorCode:
            rows.append({"GateType": "OUT", "ErrorCode": r.ErrorCode,
                         "ContainerId": r.ContainerId, "PlotOutId": r.PlotOutId,
                         "BookingId": r.BookingId, "PlotOutDate": r.PlotOutDate,
                         "PlotOutTime": r.PlotOutTime, "PlotOutStatus": "P",
                         "CreatedBy": 1, "Remarks": r.Remarks, "SealNo": r.SealNo,
                         "Transporter": r.Transporter, "VehicleNo": r.VehicleNo,
                         "ContType": r.ContType, "ContainerStatusId": r.ContainerStatusId})
    return rows
