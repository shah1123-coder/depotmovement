"""CLI entrypoint. Builds RunContext, wires logging, dispatches to Celery."""

from __future__ import annotations

import argparse

from .logging import bind, configure_logging, get_logger

log = get_logger("main")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="depot", description="Depot Movement Extraction")
    parser.add_argument("--enqueue", action="store_true",
                        help="Kick off discover_task now.")
    parser.add_argument("--insert", action="store_true",
                        help="Enable DB writeback + inserts + email completion.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Explicit no-write (default when --insert absent).")
    args = parser.parse_args(argv)

    configure_logging()
    insert = args.insert and not args.dry_run

    from .celery.tasks import discover_task

    if args.enqueue:
        res = discover_task.delay(insert=insert)
        log.info("enqueued", task_id=res.id, insert=insert)
    else:
        # Run discovery synchronously in-process.
        out = discover_task(insert=insert)
        bind(run_id=out.get("run_id", ""))
        log.info("dispatched", **out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
