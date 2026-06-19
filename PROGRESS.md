# Build Progress Log

Chronological log of every file created/changed during the build. Timestamps are
local (IST, +0530), session date 2026-06-19.

## Step 1 — Scaffold + Foundations (2026-06-19 ~15:50–16:00)

| Timestamp | File | Change |
|---|---|---|
| 2026-06-19 15:50 | `pyproject.toml` | Created — deps, console-script entry point, pytest config |
| 2026-06-19 15:50 | `Dockerfile` | Created — python:3.10-slim + ODBC 17 + mssql-tools |
| 2026-06-19 15:50 | `docker-compose.yml` | Created — redis/worker/beat/app services |
| 2026-06-19 15:50 | `.env.example` | Created — all env vars (DB creds, Redis, Celery) |
| 2026-06-19 15:52 | `config/settings.yaml` | Created — all tunables |
| 2026-06-19 15:52 | `config/regions/india.yaml` | Created — India rules (weak-booking reject) |
| 2026-06-19 15:52 | `config/regions/china.yaml` | Created — China rules (CJK markers/tokens) |
| 2026-06-19 15:54 | `src/depot/__init__.py` | Created — package marker |
| 2026-06-19 15:54 | `src/depot/settings.py` | Created — typed cached Settings, env resolution |
| 2026-06-19 15:54 | `src/depot/context.py` | Created — RunContext, temp dirs + atomic publish |
| 2026-06-19 15:56 | `src/depot/models.py` | Created — all stage-contract pydantic models |
| 2026-06-19 15:56 | `src/depot/errors.py` | Created — ErrorCode, StageResult, Failure |
| 2026-06-19 15:56 | `src/depot/logging.py` | Created — structlog JSON logging + context bind |
| 2026-06-19 15:58 | — | Verified: Python syntax ok, all 3 YAML files parse (UTF-8) |

## Step 2 — Pipeline Stages (2026-06-19 ~16:00–16:15)

| Timestamp | File | Change |
|---|---|---|
| 2026-06-19 16:00 | `src/depot/regions/__init__.py` | Created — package marker |
| 2026-06-19 16:00 | `src/depot/regions/base.py` | Created — RegionProfile, compiled regex + finders |
| 2026-06-19 16:01 | `src/depot/regions/loader.py` | Created — fail-fast YAML discovery + cache |
| 2026-06-19 16:01 | `src/depot/regions/detector.py` | Created — CJK→China/else→India |
| 2026-06-19 16:01 | `src/depot/regions/overrides/__init__.py` | Created — optional hook package |
| 2026-06-19 16:02 | — | Verified: regions load, direction/container/booking behave per spec |
| 2026-06-19 16:03 | `src/depot/cache/__init__.py` | Created — package marker |
| 2026-06-19 16:03 | `src/depot/cache/redis_client.py` | Created — shared connection pool |
| 2026-06-19 16:03 | `src/depot/cache/dedup.py` | Created — SHA-256 content hash dedup |
| 2026-06-19 16:03 | `src/depot/cache/locks.py` | Created — token-safe NX/EX distributed locks |
| 2026-06-19 16:04 | `src/depot/intake/__init__.py` | Created — package marker |
| 2026-06-19 16:04 | `src/depot/intake/mail_db.py` | Created — sqlcmd-only Mail DB access |
| 2026-06-19 16:05 | `src/depot/intake/mail_db.py` | Edited — removed unused csv/io imports (self-review) |
| 2026-06-19 16:05 | `src/depot/intake/attachments.py` | Created — fetch/filter/save attachments |
| 2026-06-19 16:05 | `src/depot/intake/registry.py` | Created — flat job fan-out |
| 2026-06-19 16:06 | `src/depot/workbook/__init__.py` | Created — package marker |
| 2026-06-19 16:06 | `src/depot/workbook/loader.py` | Created — decrypt + detection/extraction views |
| 2026-06-19 16:07 | `src/depot/workbook/grid.py` | Created — merged-cell logical grid |
| 2026-06-19 16:07 | `src/depot/workbook/sheets.py` | Created — XOR sheet eligibility |
| 2026-06-19 16:08 | `src/depot/workbook/sheets.py` | Edited — removed redundant in_remark branch (self-review) |
| 2026-06-19 16:08 | `src/depot/detect/__init__.py` | Created — package marker |
| 2026-06-19 16:08 | `src/depot/detect/headers.py` | Created — plain-text header runs, stacked-header skip |
| 2026-06-19 16:08 | `src/depot/detect/titles.py` | Created — title scan above header |
| 2026-06-19 16:08 | `src/depot/detect/boundaries.py` | Created — blank-row boundary + cell clipping |
| 2026-06-19 16:09 | `src/depot/extract/__init__.py` | Created — package marker |
| 2026-06-19 16:09 | `src/depot/extract/paths.py` | Created — path sanitize + unique_path |
| 2026-06-19 16:09 | `src/depot/extract/columns.py` | Created — generic column resolver |
| 2026-06-19 16:10 | `src/depot/extract/tables.py` | Created — clean table + row validity flag |
| 2026-06-19 16:10 | `src/depot/extract/direction.py` | Created — direction resolver + workbook fallback |
| 2026-06-19 16:11 | `src/depot/extract/gate_in.py` | Created — IN field extraction (first date/time) |
| 2026-06-19 16:11 | `src/depot/extract/gate_out.py` | Created — OUT extraction (last date/time, NO_BOOKING_ID) |
| 2026-06-19 16:11 | `src/depot/normalize/__init__.py` | Created — package marker |
| 2026-06-19 16:11 | `src/depot/normalize/fields.py` | Created — container/date/time/empty normalization |
| 2026-06-19 16:12 | — | Verified: 36 modules syntax ok |
| 2026-06-19 16:12 | `src/depot/db/__init__.py` | Created — package marker |
| 2026-06-19 16:12 | `src/depot/db/connection.py` | Created — read/write pyodbc, chunking |
| 2026-06-19 16:12 | `src/depot/db/lookups.py` | Created — batched ICMS read lookups |
| 2026-06-19 16:13 | `src/depot/db/batcher.py` | Created — one-shot LookupCache |
| 2026-06-19 16:13 | `src/depot/validate/__init__.py` | Created — package marker |
| 2026-06-19 16:13 | `src/depot/validate/booking.py` | Created — booking resolution + ECP under lock |
| 2026-06-19 16:13 | `src/depot/validate/gate_in.py` | Created — IN error priority |
| 2026-06-19 16:13 | `src/depot/validate/gate_out.py` | Created — OUT error priority |
| 2026-06-19 16:14 | `src/depot/db/persist.py` | Created — transactional bulk inserts + PlotID parse |
| 2026-06-19 16:14 | `src/depot/output/__init__.py` | Created — package marker |
| 2026-06-19 16:14 | `src/depot/output/json_writer.py` | Created — frozen-schema gate_in/out/errors JSON |
| 2026-06-19 16:15 | `src/depot/pipeline.py` | Created — per-workbook pure pipeline |
| 2026-06-19 16:15 | `src/depot/celery/__init__.py` | Created — package marker |
| 2026-06-19 16:15 | `src/depot/celery/app.py` | Created — Celery app, late acks, requeue |
| 2026-06-19 16:15 | `src/depot/celery/routing.py` | Created — intake/process/persist queues |
| 2026-06-19 16:15 | `src/depot/celery/tasks.py` | Created — discover→chord→persist tasks |
| 2026-06-19 16:16 | `src/depot/celery/beat.py` | Created — 5-min Mail DB poll schedule |
| 2026-06-19 16:16 | `src/depot/main.py` | Created — CLI entrypoint |

## Tests & Docs (2026-06-19 ~16:16–16:17)

| Timestamp | File | Change |
|---|---|---|
| 2026-06-19 16:16 | `tests/conftest.py` | Created — src path injection |
| 2026-06-19 16:16 | `tests/fixtures/build_fixtures.py` | Created — India IN/OUT sample workbooks |
| 2026-06-19 16:16 | `tests/unit/test_regions.py` | Created — region behaviour tests |
| 2026-06-19 16:16 | `tests/unit/test_grid_headers.py` | Created — grid/header/title/boundary tests |
| 2026-06-19 16:16 | `tests/unit/test_normalize.py` | Created — normalization tests |
| 2026-06-19 16:16 | `tests/unit/test_extract.py` | Created — gate_in/out extraction tests |
| 2026-06-19 16:16 | `tests/unit/test_validate.py` | Created — error-priority validation tests |
| 2026-06-19 16:16 | `tests/e2e/test_pipeline_e2e.py` | Created — full IN+OUT pipeline e2e |
| 2026-06-19 16:16 | — | Verified: 24 tests pass (unit + e2e) |
| 2026-06-19 16:17 | `README.md` | Created — quick start, CLI, architecture |
| 2026-06-19 16:17 | — | Verified: 54 modules syntax ok, 24 tests pass, heavy imports ok |
| 2026-06-19 16:17 | `PROGRESS.md` | Created — this log |
