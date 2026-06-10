#!/usr/bin/env python3
"""Watch files/api and process each stable batch of Excel attachments."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from converter import SUPPORTED_EXCEL_SUFFIXES
from pipeline import API_DIR, run_pipeline


def pending_files() -> list[Path]:
    API_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(
        (
            path
            for path in API_DIR.iterdir()
            if path.is_file()
            and not path.name.startswith("~$")
            and path.suffix.lower() in SUPPORTED_EXCEL_SUFFIXES
        ),
        key=lambda path: path.name.lower(),
    )


def snapshot(paths: list[Path]) -> dict[Path, tuple[int, int]]:
    return {path: (path.stat().st_size, path.stat().st_mtime_ns) for path in paths}


def stable_batch(delay: float) -> list[Path]:
    first = pending_files()
    if not first:
        return []
    state = snapshot(first)
    time.sleep(delay)
    second = pending_files()
    return second if set(second) == set(first) and snapshot(second) == state else []


def watch(poll_seconds: float = 2.0, stable_seconds: float = 2.0) -> None:
    while True:
        batch = stable_batch(stable_seconds)
        if batch:
            try:
                print(json.dumps(run_pipeline(batch, insert_database=True), indent=2))
            except Exception as exc:
                print(f"Pipeline failed: {exc}")
                time.sleep(poll_seconds)
        else:
            time.sleep(poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Watch the CSV API inbox.")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--stable-seconds", type=float, default=2.0)
    args = parser.parse_args()
    watch(args.poll_seconds, args.stable_seconds)


if __name__ == "__main__":
    main()
