"""RunContext: the single source of truth for every path in a run.

A run writes everything into a temporary directory first and is published
atomically into files/runs/<run_id>/ only at the end, so a crash never
leaves a half-written run behind.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .settings import Settings


class RunContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: str
    settings: Settings
    inbox_dir: Path
    temp_root: Path
    final_run_dir: Path
    run_dir: Path
    processed_dir: Path
    extraction_dir: Path
    results_dir: Path
    published: bool = False

    @classmethod
    def create(cls, settings: Settings) -> "RunContext":
        run_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        files_root = Path(settings.paths.files_root)
        inbox_dir = Path(settings.paths.inbox)
        runs_root = Path(settings.paths.runs)

        inbox_dir.mkdir(parents=True, exist_ok=True)
        runs_root.mkdir(parents=True, exist_ok=True)

        temp_root = Path(tempfile.mkdtemp(prefix=f"depot_{run_id}_", dir=str(files_root)))
        run_dir = temp_root
        processed_dir = run_dir / "processed"
        extraction_dir = run_dir / "extraction"
        results_dir = run_dir / "results"
        for d in (processed_dir, extraction_dir, results_dir,
                  results_dir / "IN", results_dir / "OUT", results_dir / "UNRESOLVED"):
            d.mkdir(parents=True, exist_ok=True)

        return cls(
            run_id=run_id,
            settings=settings,
            inbox_dir=inbox_dir,
            temp_root=temp_root,
            final_run_dir=runs_root / run_id,
            run_dir=run_dir,
            processed_dir=processed_dir,
            extraction_dir=extraction_dir,
            results_dir=results_dir,
        )

    def publish(self) -> Path:
        """Atomically move the temp run dir into its final location."""
        if self.published:
            return self.final_run_dir
        self.final_run_dir.parent.mkdir(parents=True, exist_ok=True)
        if self.final_run_dir.exists():
            shutil.rmtree(self.final_run_dir)
        os.replace(self.temp_root, self.final_run_dir)
        self.published = True
        return self.final_run_dir
