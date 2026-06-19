# Depot Movement Extraction Module

Reads daily depot Excel reports (Gate-In / Gate-Out), detects movement tables
across heterogeneous layouts (India/China), validates each container against
ICMS, and writes clean JSON (and inserts in `--insert` mode). Built for ~15k
reports/day via Celery + Redis.

## Quick start

```bash
cp .env.example .env          # fill in DB creds
docker compose up --build     # redis + worker + beat
docker compose run --rm app depot --enqueue --insert
```

Local dev:

```bash
pip install -e .[dev]
pytest                        # unit + e2e
```

## CLI

| Flag | Effect |
|---|---|
| `--enqueue` | Dispatch `discover_task` via Celery now. |
| `--insert` | Enable DB writeback, inserts and email completion. |
| `--dry-run` | Explicit no-write (default when `--insert` absent). |

## Architecture

Pure-function stages chained per workbook (`src/depot/pipeline.py`):
intake → dedup → workbook load → merged-cell logical grid → header/title/boundary
detection → table + direction extraction → field extraction (gate_in/gate_out) →
normalization → batched DB validation → JSON output → bulk insert.

Region rules live entirely in `config/regions/*.yaml`; adding a country is a new
YAML file, never a core change. Output JSON field names are frozen to the DB
schema (Section 18 of the build guide). See `GUIDE.md` for the full design.
