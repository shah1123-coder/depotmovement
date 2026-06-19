# Depot Movement Extraction Module — Build Guide

> **Who this is for.** You are building this project from scratch. Do not invent anything. Do not skip steps. Build files in the exact order given. Each section tells you the file path, what the file does, what goes inside it, and how to test it before moving on. If something is unclear, re-read the section — the answer is here.

---

## 0. What This Module Does (Read First)

Depots (container yards) email us Excel reports every day. Each report lists containers that entered the yard (**Gate-In**) or left the yard (**Gate-Out**). Every depot uses a **different** Excel layout — different columns, sheet names, languages (English for India, Chinese for China), merged cells, titles, multiple tables per sheet.

Our job: read those Excel files, find the movement tables, pull out each container's data, validate it against our database, and insert clean records into the database. Bad records are stored separately for humans to review.

**Scale target:** ~15,000 reports/day. This is why we use **Celery** (a task queue) to process many files in parallel and **Redis** (an in-memory store) to make sure we never process the same file twice.

**Two things that must NEVER change:**
1. The output JSON field names and structure (they must match the database schema exactly — see Section 18).
2. The module must stay **modular by region** so new regions (countries) can be added by dropping in one config file (see Section 7).

Everything else in this guide is the design you must follow.

---

## 1. Core Concepts & Vocabulary

| Term | Meaning |
|---|---|
| **Workbook** | One Excel file (`.xlsx`, `.xls`, encrypted Excel). |
| **Sheet** | One tab inside a workbook. |
| **Logical cell** | A normalized cell. Merged cells are flattened so one merged block = one logical cell. |
| **Logical grid** | The whole sheet rebuilt out of logical cells. Everything downstream reads this, never the raw file. |
| **Header run** | A row segment of 3+ consecutive plain-text cells — this marks the top of a table. |
| **Table region** | The rectangle of data belonging to one detected table. |
| **Direction** | `IN`, `OUT`, or `UNRESOLVED` — whether a table is Gate-In or Gate-Out. |
| **Region profile** | The set of rules (markers, regex, fallbacks) for one country (India / China). |
| **Movement record** | One extracted container row, before or after validation. |
| **Error code** | A string like `NO_CONTAINER_ID` set when a record fails a validation rule. |
| **Run** | One execution of the pipeline. All its outputs go in one timestamped folder. |
| **Job** | The processing of one single workbook file. Many jobs run in parallel. |

**Golden rules of the codebase:**
- Every stage is a **pure function**: input model in → output model + list of errors out. No global state.
- **Errors are data, not crashes.** One broken file must never stop the batch. Catch, record, continue.
- All file paths come from one `RunContext` object. Never hardcode a path anywhere else.
- A container number is the **anchor** of a row. No valid container = skip the row.

---

## 2. Technology Stack & Versions

- **Python 3.10** (fixed — Docker gives us this exact version).
- **Celery 5.x** — distributed task queue for bulk parallel processing.
- **Redis 7.x** — Celery broker/result backend **and** our dedup/lock cache.
- **openpyxl** — read `.xlsx`.
- **msoffcrypto-tool** — decrypt password-protected Excel before reading.
- **xlrd** / **pyexcel-xls** — read legacy `.xls`.
- **pyodbc** — connect to the ICMS database (with `ODBC Driver 17 for SQL Server`).
- **sqlcmd** (subprocess) — connect to the Mail database only (per existing infra rule).
- **pydantic 2.x** — typed data models and config validation.
- **PyYAML** — read the config and region files.
- **structlog** — structured logging.
- **pytest** — tests.

Everything runs inside Docker on Ubuntu. Because it is Docker, you may pin any versions you like in `pyproject.toml`; the host does not matter.

---

## 3. Project Structure (Build In This Order)

```
documents/depot_movement/
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── README.md
├── config/
│   ├── settings.yaml
│   └── regions/
│       ├── india.yaml
│       └── china.yaml
├── src/depot/
│   ├── __init__.py
│   ├── main.py
│   ├── context.py
│   ├── settings.py
│   ├── models.py
│   ├── errors.py
│   ├── logging.py
│   ├── celery/        (app.py, tasks.py, beat.py, routing.py)
│   ├── cache/         (redis_client.py, dedup.py, locks.py)
│   ├── intake/        (mail_db.py, attachments.py, registry.py)
│   ├── regions/       (base.py, loader.py, detector.py, overrides/india.py, overrides/china.py)
│   ├── workbook/      (loader.py, grid.py, sheets.py)
│   ├── detect/        (headers.py, titles.py, boundaries.py)
│   ├── extract/       (tables.py, direction.py, columns.py, gate_in.py, gate_out.py)
│   ├── normalize/     (fields.py)
│   ├── validate/      (gate_in.py, gate_out.py, booking.py)
│   ├── db/            (connection.py, lookups.py, batcher.py, persist.py)
│   └── output/        (json_writer.py)
├── files/             (runtime — inbox/ and runs/)
└── tests/             (fixtures/, unit/, e2e/)
```

**Build order:** Section 4 → 5 → 6 (foundations), then 7–18 (stages in pipeline order), then 19 (Celery/Redis), then 20 (Docker), then 21 (tests). Do not jump ahead — later files import earlier ones.

---

## 4. Foundations — Config, Settings, Context

### 4.1 `config/settings.yaml`
Holds every tunable value. No secrets in code — secrets come from environment variables (Section 20).

```yaml
paths:
  files_root: "files"
  inbox: "files/inbox"
  runs: "files/runs"
mail_db:
  server_env: "MAIL_DB_SERVER"
  default_server: "10.1.0.6"
  database: "EMail_Reader_Process_Data"
  process_name: "VISHNU_DEPOT"
icms_db:
  server_env: "ICMS_SERVER"
  default_server: "10.10.0.72"
  database: "ICMS"
  driver: "ODBC Driver 17 for SQL Server"
  chunk_size: 1000
insert_db:
  database: "archeet"      # all inserts go here (test mirror); prod target swapped via env later
redis:
  url_env: "REDIS_URL"
  default_url: "redis://redis:6379/0"
  dedup_ttl_days: 30
celery:
  broker_env: "CELERY_BROKER_URL"
  result_env: "CELERY_RESULT_BACKEND"
attachment_api:
  base_url: "https://mail-reader.sarjak.com/api/attachment/internet-id"
  skip_if_name_contains: ["ARCON"]
  keep_only_if_name_contains: ["SARJAK"]
detection:
  min_header_cells: 3
  title_scan_rows: 2
batch:
  workbook_concurrency: 8     # celery worker concurrency
gate_in_status_valid: [2, 7]
relevant_status_ids: [2, 3, 6, 7]
```

### 4.2 `src/depot/settings.py`
- Load `settings.yaml` with PyYAML.
- Validate it into a pydantic `Settings` model (fail fast on missing keys).
- Resolve server values: read the env var named by `*_env`; if unset, use `default_*`.
- Expose a single `get_settings()` that loads once and caches the result.

### 4.3 `src/depot/context.py`
- Define `RunContext` (pydantic model) created once at the start of every run.
- Fields: `run_id` (format `YYYY-MM-DD_HH-MM-SS`), `settings`, and derived paths:
  - `inbox_dir`, `run_dir = runs/<run_id>/`, `processed_dir`, `extraction_dir`, `results_dir`.
- On creation, build the run folders **in a temp location** and only move them into place at the end (atomic publish — Section 17). Provide `RunContext.create(settings)` and `RunContext.publish()`.
- **Every other module receives the `RunContext`; nobody builds paths on their own.**

---

## 5. Shared Models — `src/depot/models.py`

Define these pydantic models. They are the contracts between stages.

- `LogicalCell`: `row, end_row, start_col, end_col, value, is_horizontal_merge, is_vertical_merge`.
- `HeaderRun`: `sheet, row, start_col, end_col, cell_count, values[], cells[], title`.
- `TableRegion`: `sheet, header: HeaderRun, data_start_row, data_end_row, start_col, end_col`.
- `Direction`: enum `IN`, `OUT`, `UNRESOLVED`.
- `RawRow`: a list of cell strings + source row index.
- `GateInRecord` — extraction shape: `container_no, date, time, remark, container_status, error_code`.
- `GateOutRecord` — extraction shape: `container_id, booking_id, seal_no, plot_out_date, plot_out_time, transporter, vehicle_no, remarks, error_code`.
- `GateInValues` / `GateOutValues` — **final DB-schema shapes** (exact fields in Section 18). Keep these separate from the extraction shapes above.
- `JobResult`: `file, message_id, region, in_records[], out_records[], errors[], db_counts, status`.
- `RunSummary`: `workbooks[], dirs, db_counts, message_ids[], completed_at`.

> Why two shapes for In/Out? Extraction produces a loose, human-friendly record; validation enriches it with DB ids and maps it to the strict DB schema. Never mix the two.

---

## 6. Errors & Logging

### 6.1 `src/depot/errors.py`
- Define the error-code constants as a frozen set / Enum: `NO_CONTAINER_ID`, `DUPLICATE_RECORD`, `INVALID_CONTAINER_STATUS_ID`, `NO_BOOKING_ID`, `INVALID_ECP_COUNT`, `INVALID_CONTAINER_NUMBER`.
- Define `StageResult[T]`: holds `value: T | None` and `failures: list[Failure]`. Every stage returns this.
- Define `Failure`: `stage, file, message_id, reason, detail`.
- **Rule:** stages catch their own exceptions, wrap them in `Failure`, and return — they never raise out of the pipeline.

### 6.2 `src/depot/logging.py`
- Configure `structlog` to emit JSON lines.
- Bind `run_id` and `job_id` (= file name) so every log line is traceable.
- Expose `get_logger(name)`.

---

## 7. Region System (Modularity — Never Break This)

This is the part that must stay extensible. A new region must require **only** a new YAML file (+ optional override class) and zero core changes.

### 7.1 `config/regions/india.yaml` and `china.yaml`
Each region file declares **all** its rules declaratively:

```yaml
name: "india"
language: "en"
sheet_rules:
  exclude_if_name_contains: ["MONTH", "MASTER"]
  always_process_names: ["SHEET1"]
  direct_in_names: []
  direct_out_names: []
  recognized_names: ["GATE IN", "GATE OUT", "DAILY MOVEMENT", "DAILY REPORT", "GATE IN & OUT SUMMERY"]
regex:
  container: '\b[A-Z]{3}[UJZ]\d{7}\b'
  booking_main: '\b[A-Za-z]{3}/[A-Za-z]{3}/\d{6}\b'
  booking_fallback: '(?!x)x'          # never-matches: India rejects weak bookings
  time: '([01]?\d|2[0-3]):([0-5]\d)(:[0-5]\d)?(\s*[AP]M)?'
  vehicle: '\b[A-Z]{2}[- ]?\d{2}[- ]?[A-Z]{1,3}[- ]?\d{4}\b'
  standalone_in: '(?<![A-Za-z0-9])IN(?![A-Za-z0-9])'
  standalone_out: '(?<![A-Za-z0-9])OUT(?![A-Za-z0-9])'
  gate_in: 'GATE\s*IN'
  gate_out: 'GATE\s*OUT'
  email: '[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}'
  booked_qty: '(\d+)\s*X\s*(.+)'
markers:
  in_remark: ["remark"]
  out_remark: ["remark"]
  out_booking: []
  seal: ["seal"]
  transporter: ["transporter"]
  vehicle: []
direction_in_tokens: []     # extra literal tokens, e.g. CJK for china
direction_out_tokens: []
```

China's file is the same shape with Chinese values: `recognized` adds `进场`/`出场` to `direct_in_names`/`direct_out_names`; `booking_fallback: '^\d{6}$'`; markers add `备注`, `单号`, `场车牌`; `direction_in_tokens: ["进"]`, `direction_out_tokens: ["出"]`; vehicle regex = Chinese province-prefix plate pattern.

> **Note the deliberate misspelling `SUMMERY`** — keep it exactly; the depots' files spell it that way.

### 7.2 `src/depot/regions/base.py`
- Define `RegionProfile` (pydantic) = the parsed YAML, with compiled regex objects (case-insensitive where the spec says so) and helper methods:
  - `find_container(text) -> str | None` (returns uppercase).
  - `find_booking(text)`, `find_time(text)`, `find_vehicle(text)`, `find_date(text)`.
  - `detect_direction(text) -> Direction` (uses in/out regex + literal tokens; both found → UNRESOLVED).
  - `is_excluded_sheet(name)`, `is_forced_sheet(name)`, `is_recognized_sheet(name)`.

### 7.3 `src/depot/regions/loader.py`
- Discover every `.yaml` in `config/regions/`, validate, build a `RegionProfile`, cache by name.
- **Fail fast:** a malformed region file raises at startup, before any file is processed.

### 7.4 `src/depot/regions/detector.py`
- `detect_region(sheet_title) -> RegionProfile`: if the title contains any CJK character → China; else → India.
- This is the ONLY place language→region is decided.

### 7.5 `src/depot/regions/overrides/`
- Optional. If a region needs custom code (rare), subclass a hook here. The default needs none. Keeps the core clean.

---

## 8. Stage 1 — Intake (`src/depot/intake/`)

### 8.1 `mail_db.py`
- Connect to the Mail DB using **`sqlcmd` via subprocess only** (never pyodbc — infra rule).
- `get_pending_message_ids()`: select **distinct** `internet_message_id` from `tbl_Process_Emails` where `completed_at IS NULL`, `Process='VISHNU_DEPOT'`, and id is not blank/whitespace.
- `get_body_preview(message_id)`: return the raw `body_preview`.
- `get_sender_domain(body_preview, region_email_regex)`: find the first email match; keep `@` + everything after the **last** `@`; if none, return `"Not Found"`.
- `map_sender_to_depot(domain)`: join `PortDetails` + `LocationContacts` on `DepotContactEmail=domain` and `IsDeleted=0`; return `(PortId, PortName)` or `None`.
- `mark_completed(message_ids)`: **only called in insert mode.** Update rows where `completed_at IS NULL`, then `SELECT @@ROWCOUNT` and return it.

### 8.2 `attachments.py`
- `fetch_attachments(message_id)`: GET `{base_url}/{urlencoded-id}/external-attachments`; parse JSON `attachments[]`, each having `name`/`fileName` and base64 `contentBytes`.
- `filter_attachment(name)`: skip if name contains `ARCON`; keep only if it contains `SARJAK`; else skip.
- `save_attachment(ctx, port_id, name, content, counter)`: decode base64; save under `inbox/` as `<PortId>_<counter><ext>` if PortId resolved, else `<originalstem>_<counter><ext>`; write a sidecar `<file>.message-id` containing the `internet_message_id`.

### 8.3 `registry.py`
- `build_jobs(ctx) -> list[Job]`: for every pending message id, resolve sender/depot, fetch+filter+save attachments, and produce one `Job` per saved file with `{file_path, message_id, port_id}`.
- **Important (multiple message ids):** there can be many message ids and many attachments each. `build_jobs` fans them all out into a flat job list. These jobs are what we hand to Celery (Section 19) so they process in parallel.

---

## 9. Stage 2 — Dedup & Caching (`src/depot/cache/`)

We must never process the same file twice (15k/day = retries and duplicate emails are inevitable).

### 9.1 `redis_client.py`
- One shared Redis connection pool built from `REDIS_URL`.

### 9.2 `dedup.py`
- `content_hash(file_path)`: SHA-256 of the file bytes.
- `is_duplicate(hash) -> bool`: check Redis key `depot:seen:<hash>`.
- `mark_seen(hash)`: set the key with TTL = `dedup_ttl_days`.
- In the pipeline: hash each file; if seen, skip the whole job and log it; else mark seen and continue.

### 9.3 `locks.py`
- `acquire(key, ttl)` / `release(key)`: Redis distributed lock (e.g. `SET key val NX EX ttl`).
- Use a per-file lock so two workers can't grab the same job, and a per-booking lock during the ECP-count check (Section 16) so parallel jobs don't both consume the same booking quota.

---

## 10. Stage 3 — Workbook Loading (`src/depot/workbook/`)

### 10.1 `loader.py`
- `open_workbook(path)`:
  - If encrypted, decrypt to a temp stream with `msoffcrypto-tool` first.
  - `.xls` → load via xls reader; `.xlsx` → openpyxl.
  - Return **two views**: detection view (`data_only=False`, so formulas stay visible — they must be excluded from headers) and extraction view (`data_only=True`, evaluated values).
  - If the file can't be opened, return a `Failure` — do not raise.

### 10.2 `grid.py` — Merged-Cell Normalization (read carefully)
- For each sheet build a **merged map**: for every merged range, record its bounds and its top-left value for every `(row, col)` inside it.
- `build_logical_rows(sheet)`: for each row, scan columns left→right:
  - If the cell is the **top-left** of a merged range → emit one `LogicalCell` spanning the whole range, then jump to `end_col + 1`.
  - If the cell is **inside** a merge but not top-left → skip it.
  - If not merged → emit a `1×1` LogicalCell.
  - Set `is_horizontal_merge = end_col > start_col`, `is_vertical_merge = end_row > start_row`.
- This logical grid is what detection and extraction consume — they never touch the raw sheet again.

### 10.3 `sheets.py` — Sheet Eligibility
- `select_sheets(workbook) -> list[(sheet, RegionProfile)]`:
  - For each sheet, `detect_region(sheet.title)` gives the profile.
  - Uppercase the name. **Reject** if it contains `MONTH` or `MASTER`.
  - **Force include** if name in `always_process_names` / `direct_in_names` / `direct_out_names` (e.g. `SHEET1`, `进场`, `出场`).
  - Detect IN presence and OUT presence (region markers, else standalone regex).
  - If name matches `recognized_names`: process **unless both IN and OUT are present** (ambiguous → reject).
  - Otherwise (generic sheet): process **only if exactly one** of IN/OUT is present (XOR). Reject if both or neither.

---

## 11. Stage 4 — Table Detection (`src/depot/detect/`)

### 11.1 `headers.py`
- A LogicalCell is **plain text** only if: value is a string, non-empty after strip, and does NOT start with `=`. (Numbers, dates, formulas, blanks, None all fail.)
- Within a logical row, accumulate **consecutive** plain-text cells; a run qualifies as a header if length ≥ `min_header_cells` (3).
- Walk the sheet top→bottom. When a row yields header run(s), emit a `HeaderRun` for each, then **skip following rows that also look like headers** (prevents stacked-header duplicates).
- `start_col` = first run cell's start; `end_col` = last run cell's end.

### 11.2 `titles.py`
- For each header, scan up to 2 rows above (`header_row-1` down to `header_row-2`).
- The first row above with any non-empty logical cell is the **title row**: join its non-empty stripped values with spaces; attach to the `HeaderRun`.
- No title → continue; use the sheet name as fallback context later.

### 11.3 `boundaries.py`
- Data starts at `header.row + 1`.
- Read down until the **first fully blank logical row** (no content in any cell) → that ends the table.
- Restrict columns to `[header.start_col, header.end_col]`. Clip cells to that window: `start = max(cell.start, header.start)`, `end = min(cell.end, header.end)`. Normalize value: None → `""`, else stripped string.
- Produce a `TableRegion`.

---

## 12. Stage 5 — Table Extraction (`src/depot/extract/tables.py`)

- `extract_table(ctx, region, table_region, extraction_view) -> ExtractedTable`:
  - Build the clean tabular structure (list of rows of clipped cell strings).
  - For each row, set a **validity flag**: row is valid if any cell matches the container regex; else mark `INVALID_CONTAINER_NUMBER`.
  - Optionally persist the intermediate table as an `.xlsx` under `extraction/<workbook>/<sheet>/<sanitized title-or-sheet ≤80 chars>.xlsx` for debugging/traceability (re-apply horizontal merges, normalize first column to 1, add an `Error` column).
- **Path sanitization helper** (used here and everywhere paths are built): replace `<>:"/\|?*` and control chars with spaces, collapse whitespace, strip trailing dots, use `"untitled"` if empty, add `_1`.._999` suffix if the file is locked/exists.

---

## 13. Stage 6 — Direction Resolution (`src/depot/extract/direction.py`)

One shared resolver, used both for sheet hints and final table routing.

- `resolve_direction(table, region) -> Direction`, checking sources in priority order:
  1. Extracted table filename.
  2. Parent folder name.
  3. Original workbook name.
- Within each source use the region's IN tokens (standalone IN, `GATE IN`, CJK `进`) and OUT tokens (standalone OUT, `GATE OUT`, CJK `出`).
- Decision: both found → `UNRESOLVED`; only IN → `IN`; only OUT → `OUT`; neither → try next source.
- Workbook-level fallback: scan all extracted tables of the workbook; if exactly one direction appears across all, apply that direction (and an `-IN`/`-OUT` suffix) to ambiguous ones.
- Still ambiguous → `UNRESOLVED`: **quarantine** the table. Never guess. Quarantined tables are excluded from `results/IN`, `results/OUT`, and from insertion.
- Resolved tables are copied to `results/IN/` or `results/OUT/` as `<sanitized-workbook><suffix>.xlsx`, deduped per `(direction, basename)` with `_1`, `_2`, …

---

## 14. Stage 7 — Field Extraction (`src/depot/extract/`)

### 14.1 `columns.py` — Generic Column Resolver (reused for every field)
- `resolve_column(table, *, regex=None, markers=None, fallback_regex=None) -> col_index | None`, tried in this order:
  1. **Regex column** — the rightmost column whose cells match `regex`.
  2. **Marker column** — a column whose header matches one of `markers`.
  3. **Fallback regex column**.
- This single function resolves booking, seal, transporter, remarks, vehicle — do not write a separate finder per field.

### 14.2 `gate_in.py`
- For each row in an IN table:
  - Require a container match (region.find_container). No container → skip row.
  - Take the **first** container, **first** date, **first** time in the row.
  - Read remark from the remark column (markers `remark` / `备注`).
  - Emit `GateInRecord{container_no, date, time, remark, container_status="", error_code=""}`.

### 14.3 `gate_out.py`
- For each row in an OUT table:
  - Require a container match. No container → skip row.
  - Resolve booking via `columns.resolve_column(regex=booking_main, markers=out_booking (+`单号`), fallback_regex=booking_fallback)`.
    - Booking matches main regex OR fallback → `error_code=""`. Otherwise `error_code=NO_BOOKING_ID` (this is set now and **must survive** later validation).
  - Resolve seal (`seal`), transporter (`transporter`), remarks (`remark`/`备注`), vehicle (marker `场车牌`, else vehicle regex fallback over container rows).
  - Take the **last/rightmost** date and **last/rightmost** time in the row.
  - Emit `GateOutRecord{container_id, booking_id, seal_no, plot_out_date, plot_out_time, transporter, vehicle_no, remarks, error_code}`.

> **In vs Out date/time rule:** Gate-In uses the **first** match, Gate-Out uses the **last** match. This is intentional — do not unify it.

---

## 15. Stage 8 — Normalization (`src/depot/normalize/fields.py`)

One shared module for both directions. Apply after extraction, before validation.

- `normalize_container(text)`: case-insensitive match, output uppercase; lookup key = uppercase, spaces removed.
- `normalize_date(value)`:
  - `datetime`/`date` → `%Y-%m-%d`.
  - Text → run date regex, replace commas with spaces, collapse whitespace, try ~30 fallback formats (d/m/y, m/d/y, y/m/d across `. / - space` separators, plus `%d %b %Y`, `%d %B %Y`, `%b %d %Y`, `%B %d %Y`). If all fail, return the raw matched text.
- `normalize_time(value)`:
  - `datetime`/`time` → `%H:%M:%S.000`.
  - Text → time regex; try `%I:%M %p`, `%I:%M%p`; if those fail, rebuild from regex groups as `HH:MM:SS.000`.
- `normalize_empty(value)`: None → `""`, else stripped string. Blank optional fields stay blank; blank mandatory fields are caught by validation.

---

## 16. Stage 9 — DB Lookups & Validation (`src/depot/db/` + `src/depot/validate/`)

Because we run 15k files/day, **batch every DB read once per run** — never query per record.

### 16.1 `db/connection.py`
- One pooled connection factory using `pyodbc` + `ODBC Driver 17`.
- Separate **read** connection (ICMS) from **write** connection (`archeet` / prod via env). All inserts use the write connection.
- Chunk any `IN (...)` query at `chunk_size` (1000) ids.

### 16.2 `db/lookups.py` (read-only, batched)
- `get_container_ids(container_nos)` → map ContainerNo→ContainerId (`ContainerEntry`).
- `get_container_info(container_nos)` → status (kept only if in relevant set), `LocationPlotId`, plot name.
- `get_container_types(container_nos)` → ContainerType.
- `get_depot_names(...)` → latest depot via the CTE across `ContainerEntry/PlotInDetails/PortDetails/LocationPortMapping/LocationTypeMapping` (`IsActive=1`, `IsPrimary=1`, `LocationTypeId=2`, ranked `ROW_NUMBER() ORDER BY PlotInDate DESC`, take `rn=1`).
- `get_booking_ids(refs)` → resolve numeric refs as-is; non-numeric against `BookingDetails.BookingNo`; also try a trailing-letters-stripped variant.
- `get_booked_quantities(booking_ids)` → parse `BookedContainerQty` with the booked-qty regex; sum the numeric counts.
- `get_plotted_counts(booking_ids)` → `SELECT BookingId, COUNT(ContainerId) FROM PlotOutDetails ... GROUP BY BookingId`.
- `check_in_duplicate(container_id, date)` / `check_out_duplicate(container_id, date, booking_id)`.

### 16.3 `db/batcher.py`
- Collects all container numbers / booking refs across **all** records in the run, runs the lookups above **once**, and hands back in-memory dicts. Validation reads only these dicts (plus per-record Redis booking locks).

### 16.4 `validate/gate_in.py` — assign in this priority, stop at first hit
1. `NO_CONTAINER_ID` — no ContainerId for the container number.
2. `DUPLICATE_RECORD` — existing Plot-In for same ContainerId + PlotInDate (date portion).
3. `INVALID_CONTAINER_STATUS_ID` — status not in `{2, 7}` (attach status_id if known).

### 16.5 `validate/gate_out.py` — assign in this priority
1. **Preserve** any existing `NO_BOOKING_ID` (never overwrite).
2. `NO_CONTAINER_ID`.
3. `DUPLICATE_RECORD` — existing Plot-Out for same ContainerId + PlotOutDate + BookingId.
4. `INVALID_ECP_COUNT` — extracted qty for a booking exceeds `booked_qty − already_plotted`.

### 16.6 `validate/booking.py`
- Houses booking resolution + quantity math used by `gate_out`. Use the per-booking Redis lock (Section 9.3) so two parallel jobs don't both pass the quota check on the same booking.

---

## 17. Stage 10 — Output (`src/depot/output/json_writer.py`)

**Only JSON outputs are required** (no text reports). Write exactly these files into the run folder, matching the DB schema in Section 18.

- `gate_in.json` — every IN record mapped to `GateInValues`.
- `gate_out.json` — every OUT record mapped to `GateOutValues`.
- `gate_errors.json` — records (from both IN and OUT) where `ErrorCode` is set, **excluding** `DUPLICATE_RECORD`; each tagged with `GateType` (`IN` or `OUT`).

Then **atomic publish**: write all artifacts to the temp run dir and `os.replace`/move the whole folder into `files/runs/<run_id>/{processed,extraction,results}/` so a crash never leaves a half-written run.

---

## 18. Output Schemas & Persistence (DO NOT CHANGE FIELD NAMES)

These fields are fixed by the database schema.

### 18.1 `gate_in.json` — each item `{ "values": { ... } }`
```
PlotInID, PlotID, ContainerId, PlotInDate, PlotInStatus="P",
CreatedBy=1, Remarks, BookingId, OutBookingID=null, ContainerStatusId, ErrorCode(optional)
```

### 18.2 `gate_out.json` — each item `{ "values": { ... } }`
```
PlotOutId, BookingId, ContainerId, SealNo, Transporter, VehicleNo,
PlotOutDate, PlotOutTime, Remarks, CreatedBy=1, PlotOutStatus="P",
PlotId, ContType, ContainerStatusId, ErrorCode(optional)
```

### 18.3 `gate_errors.json`
Same record fields **plus** `GateType` in `{IN, OUT}`. Only records with an `ErrorCode`, excluding `DUPLICATE_RECORD`.

### 18.4 `db/persist.py` — inserts (insert mode only, transactional, bulk)
- **Gate-In → `dbo.PlotInDetails`**: insert `PlotID, ContainerId, PlotInDate, PlotInStatus, CreatedBy, Remarks, BookingId, EditedBy`. Fixed `CreatedBy=1, EditedBy=1, PlotInStatus='P'`. Insert **only** error-free rows with non-null `PlotID`. Never insert rows with `NO_CONTAINER_ID`, `DUPLICATE_RECORD`, `INVALID_CONTAINER_STATUS_ID`, or missing plot identity.
- **Gate-Out → `dbo.PlotOutDetails`**: insert `BookingId, ContainerId, SealNo, Transporter, VehicleNo, PlotOutDate, PlotOutTime, Remarks, CreatedBy, PlotOutStatus, PlotId, EditedBy`. Fixed `CreatedBy=1, EditedBy=1, PlotOutStatus='P'`. Only error-free rows with non-null `PlotId`. Never insert `NO_BOOKING_ID`, `NO_CONTAINER_ID`, `DUPLICATE_RECORD`, `INVALID_ECP_COUNT`, or missing plot identity.
- **Errors → `dbo.DepotMovementError`**: insert `GateType, ErrorCode, ContainerId, PlotID, PlotInID, PlotOutId, BookingId, PlotInDate, PlotOutDate, PlotOutTime, PlotInStatus, PlotOutStatus, OutBookingID, CreatedBy, Remarks, SealNo, Transporter, VehicleNo, ContType, ContainerStatusId`.
- Use **executemany / bulk insert** inside one transaction per table per run for throughput.
- `PlotID`/`PlotId` is derived from the attachment filename: integer prefix before the first underscore (`123_1.xlsx → 123`).

---

## 19. Bulk Processing — Celery + Redis (`src/depot/celery/`)

This is how we scale to 15k/day and how multiple message ids are handled in parallel.

### 19.1 `app.py`
- Create the Celery app; broker and result backend both = Redis (`CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`).
- Set `worker_concurrency` from `batch.workbook_concurrency`, `acks_late=True`, `task_reject_on_worker_lost=True` (so a crashed worker re-queues its job, not loses it), and a sane `task_time_limit`.

### 19.2 `routing.py`
- Three queues: `intake`, `process`, `persist`. Route tasks to keep heavy parsing off the intake/IO path.

### 19.3 `tasks.py`
- `discover_task()`: runs Stage 1 (`registry.build_jobs`) — fans **every** message id + attachment into individual `process_workbook` tasks. This is exactly how multiple matching message ids are handled: each becomes its own independent Celery task.
- `process_workbook_task(job)`: the per-file pipeline (dedup check → load → detect → extract → normalize → validate → write JSON). Returns a `JobResult`. Idempotent: dedup via Redis content-hash means a re-delivered task is a no-op.
- `persist_task(run_id)`: gathers all JobResults of the run, runs batched DB lookups + bulk inserts, then (insert mode) `mark_completed(message_ids)`.
- Wrap the run with a Celery **chord**: `group(process_workbook_task for each job) | persist_task` so persistence happens once, after all files finish.

### 19.4 `beat.py`
- Celery Beat schedule that periodically fires `discover_task()` to poll the Mail DB for new pending emails.

### 19.5 `main.py`
- CLI entrypoint. Flags: `--enqueue` (kick off `discover_task` now), `--insert` (enable writeback + DB inserts; without it, dry-run: produce JSON, no DB writes, no email completion), `--dry-run` (explicit no-write).
- Builds the `RunContext`, wires logging, dispatches to Celery.

---

## 20. Docker & Deployment

### 20.1 `Dockerfile`
- Base `python:3.10-slim`. Install OS deps: `unixodbc`, the Microsoft `ODBC Driver 17` + `mssql-tools` (for `sqlcmd`), build tools.
- Copy project, `pip install .` from `pyproject.toml`.
- Default command runs a Celery worker; compose overrides for beat/CLI.

### 20.2 `docker-compose.yml`
- Services: `redis`, `worker` (Celery worker), `beat` (Celery beat), `app` (one-off CLI runs). All share an env file and a mounted `files/` volume.

### 20.3 `.env.example`
- List every env var: `MAIL_DB_SERVER`, `ICMS_SERVER`, DB user/password, `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, insert-target DB. Real `.env` is never committed.

### 20.4 `pyproject.toml`
- Declare all deps from Section 2 with pinned versions, package metadata, console-script entry point → `depot.main`.

---

## 21. Testing (`tests/`) — Do This For Every Stage

- `tests/fixtures/`: small sample workbooks for India and China (merged cells, titles, multi-table, encrypted, IN-only, OUT-only, ambiguous, no-container).
- `tests/unit/`: one test file per stage. Each calls the stage's pure function with a fixture model and asserts the output model + error list. Cover edge cases explicitly: merged headers, stacked headers, blank-row termination, formula cells excluded from headers, first-vs-last date for In/Out, booking fallback behavior per region, error-code priority order, dedup skip.
- `tests/e2e/`: feed a fixture workbook through the whole pipeline (Celery in eager/synchronous mode, Redis via a test container or fakeredis) and assert the three JSON files match golden files exactly.
- **Definition of done for a file:** its unit tests pass before you move to the next file.

---

## 22. Build Checklist (Tick In Order)

1. `pyproject.toml`, `Dockerfile`, `docker-compose.yml`, `.env.example`.
2. `settings.yaml` + `settings.py` + `context.py`.
3. `models.py`, `errors.py`, `logging.py`.
4. Region files + `regions/` (base, loader, detector).
5. `cache/` (redis, dedup, locks).
6. `intake/` (mail_db, attachments, registry).
7. `workbook/` (loader, grid, sheets).
8. `detect/` (headers, titles, boundaries).
9. `extract/` (tables, direction, columns, gate_in, gate_out).
10. `normalize/fields.py`.
11. `db/` (connection, lookups, batcher, persist) + `validate/`.
12. `output/json_writer.py`.
13. `celery/` (app, routing, tasks, beat) + `main.py`.
14. Tests for every stage; then run e2e; then `docker compose up`.

**Never violate:** errors-as-data, paths-from-RunContext, container-is-anchor, region-rules-in-config-only, output-schema-is-frozen, dedup-before-process, batch-DB-reads, atomic-publish.
