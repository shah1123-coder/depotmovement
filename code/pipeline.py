#!/usr/bin/env python3
"""Run conversion, extraction, classification, and IN/OUT reporting."""

from __future__ import annotations

import argparse
import importlib
import io
import json
import shutil
import uuid
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

import extract
import movement
import out
from converter import SUPPORTED_EXCEL_SUFFIXES
from database import (
    insert_generated_payloads,
    mark_process_emails_completed,
    reset_generated_payloads,
)


in_report = importlib.import_module("in")
CSV_ROOT = Path(__file__).resolve().parents[1]
FILES_ROOT = CSV_ROOT / "files"
API_DIR = FILES_ROOT / "api"
PROCESSED_ROOT = FILES_ROOT / "processed"
EXTRACTION_ROOT = FILES_ROOT / "extraction"
RESULTS_ROOT = FILES_ROOT / "results"


def configure_run_paths(run_root: Path) -> None:
    processed = run_root / "processed"
    extraction = run_root / "extraction"
    results = run_root / "results"

    extract.PROCESSED_DIR = processed
    extract.EXTRACTION_DIR = extraction
    movement.EXTRACTION_DIR = extraction
    movement.RESULTS_DIR = results

    in_report.IN_DIR = results / "IN"
    in_report.OUTPUT_PATH = results / "in.txt"
    out.OUT_DIR = results / "OUT"
    out.OUTPUT_PATH = results / "out.txt"

    import database

    database.RESULTS_DIR = results
    database.GATE_IN_JSON = results / "gate_in.json"
    database.GATE_OUT_JSON = results / "gate_out.json"
    database.GATE_ERRORS_JSON = results / "gate_errors.json"


def completion_stamp(completed_at: datetime) -> str:
    return completed_at.strftime("%Y-%m-%d_%H-%M-%S")


def message_id_path(attachment_path: Path) -> Path:
    return attachment_path.with_name(f"{attachment_path.name}.message-id")


def message_ids_for_sources(sources: list[Path]) -> list[str]:
    message_ids: set[str] = set()
    for source in sources:
        metadata = message_id_path(source)
        if metadata.is_file():
            message_id = metadata.read_text(encoding="utf-8").strip()
            if message_id:
                message_ids.add(message_id)
    return sorted(message_ids)


def available_run_path(root: Path, stamp: str) -> Path:
    candidate = root / stamp
    index = 1
    while candidate.exists():
        candidate = root / f"{stamp}_{index}"
        index += 1
    return candidate


def finalize_run(run_root: Path, stamp: str) -> dict[str, Path]:
    finalized: dict[str, Path] = {}
    for name, root in (
        ("processed", PROCESSED_ROOT),
        ("extraction", EXTRACTION_ROOT),
        ("results", RESULTS_ROOT),
    ):
        source = run_root / name
        source.mkdir(parents=True, exist_ok=True)
        root.mkdir(parents=True, exist_ok=True)
        target = available_run_path(root, stamp)
        source.replace(target)
        finalized[name] = target
    shutil.rmtree(run_root, ignore_errors=True)
    return finalized


def archive_inputs(inputs: list[Path], processed_dir: Path) -> None:
    processed_dir.mkdir(parents=True, exist_ok=True)
    for source in inputs:
        if not source.is_file() or source.parent.resolve() != API_DIR.resolve():
            continue
        target = processed_dir / source.name
        if target.exists():
            target.unlink()
        source.replace(target)
        metadata = message_id_path(source)
        if metadata.is_file():
            metadata.replace(processed_dir / metadata.name)


def discover_workbooks(inputs: list[Path]) -> list[Path]:
    workbooks: dict[Path, None] = {}

    for input_path in inputs:
        path = input_path.expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Input does not exist: {path}")

        candidates = path.rglob("*") if path.is_dir() else [path]
        for candidate in candidates:
            if (
                candidate.is_file()
                and not candidate.name.startswith("~$")
                and candidate.suffix.lower() in SUPPORTED_EXCEL_SUFFIXES
            ):
                workbooks[candidate.resolve()] = None

    if not workbooks:
        raise ValueError("No supported Excel workbooks were found.")
    return sorted(workbooks, key=lambda path: str(path).lower())


def run_pipeline(
    inputs: list[Path],
    min_cells: int = 3,
    insert_database: bool = False,
) -> dict[str, object]:
    FILES_ROOT.mkdir(parents=True, exist_ok=True)
    run_root = FILES_ROOT / ".running" / uuid.uuid4().hex
    try:
        return _run_pipeline_inner(
            inputs, run_root, min_cells=min_cells, insert_database=insert_database
        )
    except Exception:
        # Never leave a half-finished temp run behind on failure.
        shutil.rmtree(run_root, ignore_errors=True)
        raise


def _run_pipeline_inner(
    inputs: list[Path],
    run_root: Path,
    min_cells: int = 3,
    insert_database: bool = False,
) -> dict[str, object]:
    configure_run_paths(run_root)
    reset_generated_payloads()
    workbook_results: list[dict[str, object]] = []
    sources = discover_workbooks(inputs)
    internet_message_ids = message_ids_for_sources(sources)

    for source in sources:
        try:
            processed = extract.prepare_input_workbook(source)
            extraction_root = extract.extraction_root_for_workbook(processed)
            tables = extract.detect_tables(processed, min_cells=min_cells)
            saved_tables = extract.write_table_workbooks(tables, extraction_root)
            workbook_results.append(
                {
                    "source": str(source),
                    "processed": str(processed),
                    "extraction_root": str(extraction_root),
                    "outputs": [table.output for table in saved_tables if table.output],
                }
            )
        except Exception as exc:
            # A single corrupt/locked workbook must not abort the whole batch.
            workbook_results.append({"source": str(source), "error": str(exc)})

    with redirect_stdout(io.StringIO()):
        movement.categorize_and_copy()
    in_output = in_report.build_report(synchronize=False)
    out_output = out.build_report(synchronize=False)
    database_result = insert_generated_payloads() if insert_database else None
    archive_inputs(sources, extract.PROCESSED_DIR)
    completed_at = datetime.now()
    stamp = completion_stamp(completed_at)
    finalized = finalize_run(run_root, stamp)
    processed_dir = finalized["processed"]
    extraction_dir = finalized["extraction"]
    results_dir = finalized["results"]
    completed_emails = (
        mark_process_emails_completed(internet_message_ids, completed_at)
        if insert_database
        else 0
    )

    return {
        "workbooks": workbook_results,
        "processed_dir": str(processed_dir),
        "extraction_dir": str(extraction_dir),
        "results_dir": str(results_dir),
        "in_report": str(results_dir / "in.txt"),
        "out_report": str(results_dir / "out.txt"),
        "gate_in_json": str(results_dir / "gate_in.json"),
        "gate_out_json": str(results_dir / "gate_out.json"),
        "gate_errors_json": str(results_dir / "gate_errors.json"),
        "database": database_result,
        "internet_message_ids": internet_message_ids,
        "completed_emails": completed_emails,
        "completed_at": completed_at.isoformat(sep=" ", timespec="seconds"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the complete Excel extraction pipeline.")
    parser.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        help="Excel files/folders. Default: Downloads\\csv\\files\\api",
    )
    parser.add_argument(
        "--min-cells",
        type=int,
        default=3,
        help="Minimum logical text cells needed for a header run. Default: 3",
    )
    parser.add_argument(
        "--insert",
        action="store_true",
        help="Insert valid movement payloads and error payloads into archeet.",
    )
    args = parser.parse_args()
    inputs = args.inputs or [API_DIR]
    print(
        json.dumps(
            run_pipeline(
                inputs,
                min_cells=args.min_cells,
                insert_database=args.insert,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
