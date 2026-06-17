# Depot File Extraction Module — Complete Implementation Guide

> **Audience:** Junior developers, day one. You can build this module end-to-end by
> following this guide top to bottom and copying the code exactly as written.
>
> **Authoritative sources:** `WORKFLOW.md` (logical workflow), `TECHNICAL.md`
> (technical rules + regex), and the two region contract files `countries/india.py`
> and `countries/china.py`. This guide turns those into working code.
>
> **Runtime:** Ubuntu Linux + **Python 3.10** in a **plain virtual environment**
> (no Docker). All database access is done through the Microsoft `sqlcmd` CLI as a
> subprocess — there is no `pyodbc` and no native build step.

---

## Table of Contents

1. [What this module does](#1-what-this-module-does)
2. [High-level architecture](#2-high-level-architecture)
3. [Repository layout](#3-repository-layout)
4. [Environment setup (Ubuntu, Python 3.10, venv)](#4-environment-setup)
5. [Configuration (`info.txt` / env vars)](#5-configuration)
6. [Region contracts — `countries/`](#6-region-contracts--countries)
7. [`converter.py` — legacy `.xls` → `.xlsx`](#7-converterpy)
8. [`extract.py` — headers, tables, intermediate extraction](#8-extractpy)
9. [`movement.py` — IN/OUT classification & routing](#9-movementpy)
10. [`db/icms_client.py` — database access layer](#10-dbicms_clientpy)
11. [`in.py` — Gate-In extraction & validation](#11-inpy)
12. [`out.py` — Gate-Out extraction & validation](#12-outpy)
13. [`database.py` — JSON payloads, errors, inserts](#13-databasepy)
14. [`pipeline.py` — the orchestrator](#14-pipelinepy)
15. [Email intake — `api/`](#15-email-intake--api)
16. [End-to-end run & expected outputs](#16-end-to-end-run--expected-outputs)
17. [Error-code reference](#17-error-code-reference)
18. [Acceptance checklist](#18-acceptance-checklist)
19. [Adding a new region](#19-adding-a-new-region)

---

## 1. What this module does

The module ingests depot report Excel files (one per depot, every layout
different), works out whether each file is **India** (English) or **China**
(contains Chinese characters), dynamically finds the Gate-In / Gate-Out tables
inside it, extracts every row that contains a valid container number, normalizes
the fields, validates the records against the ICMS database, and produces:

- Human-readable reports: `in.txt`, `out.txt`
- Structured JSON: `gate_in.json`, `gate_out.json`, `gate_errors.json`
- Intermediate extracted tables (`.xlsx`) for audit
- Optional database inserts of clean records and error records

Everything for one execution is grouped under a timestamped run folder.

**The container number is the anchor.** A data row is only a movement record if
it contains a valid container number: three letters, a fourth letter in
`U`/`J`/`Z`, then seven digits — matched case-insensitively, output uppercased:

```
\b[A-Z]{3}[UJZ]\d{7}\b
```

---

## 2. High-level architecture

```
                        files/api/*.xlsx (or .xls)
                                  │
                                  ▼
        ┌──────────────────────────────────────────────┐
        │ pipeline.py   (orchestrates one isolated run)  │
        └──────────────────────────────────────────────┘
            │            │              │            │
            ▼            ▼              ▼            ▼
      converter.py   extract.py    movement.py   in.py / out.py
      (.xls→.xlsx)   (headers,     (IN/OUT       (extract + validate
                      tables)       routing)      + DB lookups)
                                                      │
                                                      ▼
                                                 database.py
                                          (gate_in/out/errors JSON,
                                           optional DB inserts)
                                                      │
                                                      ▼
                                          db/icms_client.py
                                          (sqlcmd subprocess)
```

**Module responsibilities**

| Module | Responsibility |
|---|---|
| `countries/india.py`, `china.py` | Region regex + markers + fallbacks (the contract). |
| `countries/__init__.py` | Pick region by language; expose patterns/fallbacks/selection. |
| `converter.py` | Convert legacy `.xls`/`.xlt` BIFF workbooks to `.xlsx`. |
| `extract.py` | Merged-cell map, logical rows, header detection, table boundaries, intermediate `.xlsx`. |
| `movement.py` | Decide IN/OUT per table, copy into `results/IN` and `results/OUT`. |
| `in.py` | Gate-In field extraction + validation → records. |
| `out.py` | Gate-Out field extraction + validation → records. |
| `database.py` | Build JSON payloads, error output, orchestrate inserts. |
| `db/icms_client.py` | All SQL via `sqlcmd`. |
| `pipeline.py` | Run everything atomically, produce run summary. |
| `api/processor.py`, `api/sender_extractor.py` | Email intake: discover, resolve sender, download attachments. |

---

## 3. Repository layout

Create exactly this tree. The repository root is the `csv/` folder; **all paths
are resolved relative to it** and **all commands are run from it**.

```
csv/
├── info.txt                     # configuration (see §5)
├── code/
│   ├── requirements.txt
│   ├── converter.py
│   ├── extract.py
│   ├── movement.py
│   ├── in.py
│   ├── out.py
│   ├── database.py
│   ├── pipeline.py
│   ├── countries/
│   │   ├── __init__.py
│   │   ├── india.py
│   │   ├── china.py
│   │   └── template.py
│   └── api/
│       ├── processor.py
│       └── sender_extractor.py
├── depot_report/
│   └── code/
│       └── db/
│           ├── __init__.py
│           └── icms_client.py
└── files/
    ├── api/                     # incoming attachments land here
    ├── processed/
    ├── extraction/
    └── results/
```

> **Why `depot_report/code/db`?** `in.py`, `out.py`, and `database.py` add this
> directory to `sys.path` and import `from db.icms_client import ...`. Keep the
> path exactly as shown so those imports resolve.

Create the directories:

```bash
mkdir -p csv/code/countries csv/code/api
mkdir -p csv/depot_report/code/db
mkdir -p csv/files/api csv/files/processed csv/files/extraction csv/files/results
```

---

## 4. Environment setup

Target: **Ubuntu 22.04 LTS, Python 3.10, plain venv. No Docker.**

### 4.1 System packages

```bash
sudo apt-get update
sudo apt-get install -y python3.10 python3.10-venv python3-pip
```

Install Microsoft `sqlcmd` (mssql-tools18) — required because all DB access goes
through the `sqlcmd` CLI:

```bash
curl https://packages.microsoft.com/keys/microsoft.asc | sudo tee /etc/apt/trusted.gpg.d/microsoft.asc
curl https://packages.microsoft.com/config/ubuntu/22.04/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install -y mssql-tools18 unixodbc-dev
echo 'export PATH="$PATH:/opt/mssql-tools18/bin"' >> ~/.bashrc
source ~/.bashrc
sqlcmd -?    # must print usage
```

> If your `sqlcmd` is `sqlcmd18` or installed elsewhere, set `SQLCMD_PATH` in
> `info.txt` (see §5) to its absolute path.

### 4.2 Python venv + dependencies

`code/requirements.txt`:

```text
et_xmlfile==2.0.0
openpyxl==3.1.5
xlrd==2.0.2
```

> `xlrd==2.0.2` reads legacy `.xls` (BIFF). `openpyxl` reads/writes `.xlsx`.
> Nothing else is needed; the standard library covers JSON, regex, subprocess.

```bash
cd csv
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r code/requirements.txt
python -c "import openpyxl, xlrd, et_xmlfile; print('Python dependencies OK')"
```

### 4.3 Smoke test the CLIs (after the code exists)

```bash
python code/pipeline.py --help
python code/extract.py --help
python code/converter.py --help
```

---

## 5. Configuration

The repo includes `info.txt` at the `csv/` root. Each module seeds
`os.environ` from it **without overriding** variables already set in the
environment (environment variables win). Format is `KEY=VALUE`, one per line;
`#` lines and blank lines are ignored; surrounding quotes are stripped.

`csv/info.txt` (example):

```text
# --- ICMS (read + reconciliation) ---
ICMS_SERVER=10.10.0.72
ICMS_DATABASE=ICMS
ICMS_USER=
ICMS_PASSWORD=<PLACEHOLDER_PASSWORD>

# --- Mail / process database (intake + write-back) ---
MAIL_DB_SERVER=10.1.0.6
MAIL_DB_USER=
MAIL_DB_PASSWORD=<PLACEHOLDER_PASSWORD>
PROCESS_EMAIL_DATABASE=EMail_Reader_Process_Data

# --- sqlcmd executable ---
SQLCMD_PATH=sqlcmd
```

Rules:

- Leave `*_USER` and `*_PASSWORD` blank to use integrated auth (`sqlcmd -E`).
- Keep `SQLCMD_PATH=sqlcmd` if it is on `PATH`, otherwise use the absolute path.

The loader (used verbatim in `icms_client.py` and `api/processor.py`):

```python
def _load_env() -> None:
    """Seed os.environ from csv/info.txt without overriding existing variables."""
    env_path = CSV_ROOT / "info.txt"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)
```

---

## 6. Region contracts — `countries/`

This is the heart of the modular design. Each region exposes the **same seven
public names**. The core engine never hard-codes India/China regex — it asks the
region module. Adding a country = adding one file (see §19).

### 6.1 Required public names (the contract)

Every region module **must** define:

| Name | Type | Meaning |
|---|---|---|
| `COUNTRY_CODE` | `str` | e.g. `"IN"`, `"CN"`. |
| `COUNTRY_NAME` | `str` | e.g. `"India"`. |
| `LANGUAGE_PATTERN` | compiled regex | Matches text of this region's language. |
| `SHEET_SELECTION` | `SheetSelection` | Sheet-name selection rules. |
| `IN_PATTERNS` | `InPatterns` | Gate-In regex set. |
| `OUT_PATTERNS` | `OutPatterns` | Gate-Out regex set. |
| `FALLBACKS` | `Fallbacks` | Markers + parsing fallbacks + default error. |

### 6.2 `countries/india.py` (copy exactly)

```python
"""India/English worksheet integration."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Pattern


# Integration metadata and worksheet-language detection.
COUNTRY_CODE = "IN"
COUNTRY_NAME = "India"
LANGUAGE_PATTERN = re.compile(r"[A-Za-z]")


@dataclass(frozen=True)
class InPatterns:
    container_number: Pattern[str]
    date: Pattern[str]
    time: Pattern[str]


@dataclass(frozen=True)
class OutPatterns:
    container_number: Pattern[str]
    booking_id: Pattern[str]
    vehicle_number: Pattern[str]
    date: Pattern[str]
    time: Pattern[str]


@dataclass(frozen=True)
class Fallbacks:
    date_formats: tuple[str, ...]
    time_formats: tuple[str, ...]
    whitespace_pattern: Pattern[str]
    default_error_code: str
    in_remark_markers: tuple[str, ...]
    out_booking_markers: tuple[str, ...]
    out_booking_fallback: Pattern[str]
    out_seal_markers: tuple[str, ...]
    out_transporter_markers: tuple[str, ...]
    out_remark_markers: tuple[str, ...]
    out_vehicle_markers: tuple[str, ...]


@dataclass(frozen=True)
class SheetSelection:
    standalone_in: Pattern[str]
    standalone_out: Pattern[str]
    gate_in: Pattern[str]
    gate_out: Pattern[str]
    recognized_names: Pattern[str]
    in_language_marker: str
    out_language_marker: str
    excluded_name_parts: tuple[str, ...]
    always_process_names: tuple[str, ...]
    direct_in_names: tuple[str, ...]
    direct_out_names: tuple[str, ...]


# English-only worksheet-selection regex, exclusions, and fallbacks.
SHEET_SELECTION = SheetSelection(
    standalone_in=re.compile(r"(?<![a-zA-Z0-9])IN(?![a-zA-Z0-9])", re.IGNORECASE),
    standalone_out=re.compile(r"(?<![a-zA-Z0-9])OUT(?![a-zA-Z0-9])", re.IGNORECASE),
    gate_in=re.compile(r"GATE\s*IN", re.IGNORECASE),
    gate_out=re.compile(r"GATE\s*OUT", re.IGNORECASE),
    recognized_names=re.compile(
        r"GATE\s*IN|GATE\s*OUT|DAILY\s*MOVEMENT|DAILY\s*REPORT|"
        r"GATE\s*IN\s*&\s*OUT\s*SUMMERY",
        re.IGNORECASE,
    ),
    in_language_marker="",
    out_language_marker="",
    excluded_name_parts=("MONTH", "MASTER"),
    always_process_names=("SHEET1",),
    direct_in_names=(),
    direct_out_names=(),
)


# Shared regex used by both IN and OUT processing.
CONTAINER_NUMBER = re.compile(r"\b[A-Z]{3}[UJZ]\d{7}\b", re.IGNORECASE)
DATE_PATTERN = re.compile(
    r"\b(?:"
    r"\d{1,2}[./ -]\d{1,2}[./ -]\d{2,4}|"
    r"\d{4}[./ -]\d{1,2}[./ -]\d{1,2}|"
    r"\d{1,2}[/ -]+[A-Za-z]{3,9}[/ -]+\d{2,4}|"
    r"[A-Za-z]{3,9}[/ -]+\d{1,2}[, /-]+\d{2,4}"
    r")\b",
    re.IGNORECASE,
)
TIME_PATTERN = re.compile(
    r"\b([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?(\s*[AP]M)?\b",
    re.IGNORECASE,
)

# Regex used only by OUT processing.
BOOKING_ID = re.compile(r"\b[A-Za-z]{3}/[A-Za-z]{3}/\d{6}\b")
VEHICLE_NUMBER = re.compile(
    r"\b[A-Z]{2}[- ]?\d{2}[- ]?[A-Z]{1,3}[- ]?\d{4}\b",
    re.IGNORECASE,
)

# Explicit direction contracts consumed by in.py and out.py.
IN_PATTERNS = InPatterns(CONTAINER_NUMBER, DATE_PATTERN, TIME_PATTERN)
OUT_PATTERNS = OutPatterns(
    CONTAINER_NUMBER,
    BOOKING_ID,
    VEHICLE_NUMBER,
    DATE_PATTERN,
    TIME_PATTERN,
)

# Non-regex defaults and parsing fallbacks owned by this integration.
FALLBACKS = Fallbacks(
    date_formats=(
        "%d/%m/%Y", "%d/%m/%y", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d",
        "%d.%m.%Y", "%d.%m.%y", "%m.%d.%Y", "%m.%d.%y", "%Y.%m.%d",
        "%d-%m-%Y", "%d-%m-%y", "%m-%d-%Y", "%m-%d-%y", "%Y-%m-%d",
        "%d %m %Y", "%d %m %y", "%m %d %Y", "%m %d %y", "%Y %m %d",
        "%d %b %Y", "%d %b %y", "%d %B %Y", "%d %B %y",
        "%d-%b-%Y", "%d-%b-%y", "%d-%B-%Y", "%d-%B-%y",
        "%b %d %Y", "%b %d %y", "%B %d %Y", "%B %d %y",
    ),
    time_formats=("%I:%M %p", "%I:%M%p"),
    whitespace_pattern=re.compile(r"\s+"),
    default_error_code="NO_BOOKING_ID",
    in_remark_markers=("remark",),
    out_booking_markers=(),
    out_booking_fallback=re.compile(r"(?!x)x"),
    out_seal_markers=("seal",),
    out_transporter_markers=("transporter",),
    out_remark_markers=("remark",),
    out_vehicle_markers=(),
)
```

> **Note on India's `out_booking_fallback = (?!x)x`** — this is a deliberate
> *never-match* pattern. India does **not** accept weak numeric booking
> fallbacks; only the strict `XXX/XXX/######` format counts.

### 6.3 `countries/china.py` (copy exactly)

```python
"""China/Chinese worksheet integration."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Pattern


# Integration metadata and worksheet-language detection.
COUNTRY_CODE = "CN"
COUNTRY_NAME = "China"
LANGUAGE_PATTERN = re.compile(r"[㐀-䶿一-鿿豈-﫿]")


@dataclass(frozen=True)
class InPatterns:
    container_number: Pattern[str]
    date: Pattern[str]
    time: Pattern[str]


@dataclass(frozen=True)
class OutPatterns:
    container_number: Pattern[str]
    booking_id: Pattern[str]
    vehicle_number: Pattern[str]
    date: Pattern[str]
    time: Pattern[str]


@dataclass(frozen=True)
class Fallbacks:
    date_formats: tuple[str, ...]
    time_formats: tuple[str, ...]
    whitespace_pattern: Pattern[str]
    default_error_code: str
    in_remark_markers: tuple[str, ...]
    out_booking_markers: tuple[str, ...]
    out_booking_fallback: Pattern[str]
    out_seal_markers: tuple[str, ...]
    out_transporter_markers: tuple[str, ...]
    out_remark_markers: tuple[str, ...]
    out_vehicle_markers: tuple[str, ...]


@dataclass(frozen=True)
class SheetSelection:
    standalone_in: Pattern[str]
    standalone_out: Pattern[str]
    gate_in: Pattern[str]
    gate_out: Pattern[str]
    recognized_names: Pattern[str]
    in_language_marker: str
    out_language_marker: str
    excluded_name_parts: tuple[str, ...]
    always_process_names: tuple[str, ...]
    direct_in_names: tuple[str, ...]
    direct_out_names: tuple[str, ...]


# Chinese/English worksheet-selection regex, markers, exclusions, and fallbacks.
SHEET_SELECTION = SheetSelection(
    standalone_in=re.compile(r"(?<![a-zA-Z0-9])IN(?![a-zA-Z0-9])", re.IGNORECASE),
    standalone_out=re.compile(r"(?<![a-zA-Z0-9])OUT(?![a-zA-Z0-9])", re.IGNORECASE),
    gate_in=re.compile(r"GATE\s*IN", re.IGNORECASE),
    gate_out=re.compile(r"GATE\s*OUT", re.IGNORECASE),
    recognized_names=re.compile(
        r"GATE\s*IN|GATE\s*OUT|DAILY\s*MOVEMENT|DAILY\s*REPORT|"
        r"GATE\s*IN\s*&\s*OUT\s*SUMMERY",
        re.IGNORECASE,
    ),
    in_language_marker="进场",   # 进场
    out_language_marker="出场",  # 出场
    excluded_name_parts=("MONTH", "MASTER"),
    always_process_names=("SHEET1",),
    direct_in_names=("进场",),   # 进场
    direct_out_names=("出场",),  # 出场
)


# Shared regex used by both IN and OUT processing.
CONTAINER_NUMBER = re.compile(r"\b[A-Z]{3}[UJZ]\d{7}\b", re.IGNORECASE)
DATE_PATTERN = re.compile(
    r"\b(?:"
    r"\d{1,2}[./ -]\d{1,2}[./ -]\d{2,4}|"
    r"\d{4}[./ -]\d{1,2}[./ -]\d{1,2}|"
    r"\d{1,2}[/ -]+[A-Za-z]{3,9}[/ -]+\d{2,4}|"
    r"[A-Za-z]{3,9}[/ -]+\d{1,2}[, /-]+\d{2,4}"
    r")\b",
    re.IGNORECASE,
)
TIME_PATTERN = re.compile(
    r"\b([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?(\s*[AP]M)?\b",
    re.IGNORECASE,
)

# Regex used only by OUT processing.
BOOKING_ID = re.compile(r"\b[A-Za-z]{3}/[A-Za-z]{3}/\d{6}\b")
VEHICLE_NUMBER = re.compile(
    r"[京津沪渝冀豫云辽黑湘"
    r"皖鲁新苏浙赣鄂桂甘晋"
    r"蒙陕吉闽贵粤青藏川宁"
    r"琼][A-Z][·\-]?[A-Z0-9]{5,6}\b",
    re.IGNORECASE,
)

# Explicit direction contracts consumed by in.py and out.py.
IN_PATTERNS = InPatterns(CONTAINER_NUMBER, DATE_PATTERN, TIME_PATTERN)
OUT_PATTERNS = OutPatterns(
    CONTAINER_NUMBER,
    BOOKING_ID,
    VEHICLE_NUMBER,
    DATE_PATTERN,
    TIME_PATTERN,
)

# Non-regex defaults and parsing fallbacks owned by this integration.
FALLBACKS = Fallbacks(
    date_formats=(
        "%d/%m/%Y", "%d/%m/%y", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d",
        "%d.%m.%Y", "%d.%m.%y", "%m.%d.%Y", "%m.%d.%y", "%Y.%m.%d",
        "%d-%m-%Y", "%d-%m-%y", "%m-%d-%Y", "%m-%d-%y", "%Y-%m-%d",
        "%d %m %Y", "%d %m %y", "%m %d %Y", "%m %d %y", "%Y %m %d",
        "%d %b %Y", "%d %b %y", "%d %B %Y", "%d %B %y",
        "%d-%b-%Y", "%d-%b-%y", "%d-%B-%Y", "%d-%B-%y",
        "%b %d %Y", "%b %d %y", "%B %d %Y", "%B %d %y",
    ),
    time_formats=("%I:%M %p", "%I:%M%p"),
    whitespace_pattern=re.compile(r"\s+"),
    default_error_code="NO_BOOKING_ID",
    in_remark_markers=("remark", "备注"),       # 备注
    out_booking_markers=("单号",),              # 单号
    out_booking_fallback=re.compile(r"^\d{6}$"),
    out_seal_markers=("seal",),
    out_transporter_markers=("transporter",),
    out_remark_markers=("remark", "备注"),      # 备注
    out_vehicle_markers=("场车牌",),        # 场车牌
)
```

> **Key India vs. China differences to internalize:**
> - China detects language by CJK characters; India is the default.
> - China's booking fallback accepts a bare 6-digit number (`^\d{6}$`); India's never matches.
> - China adds Chinese markers: remark `备注`, booking `单号`, vehicle `场车牌`, and direct sheets `进场`/`出场`.
> - China's vehicle regex is a province-character prefix + plate body; India's is the standard Indian plate.

### 6.4 `countries/__init__.py` (region selector)

The selector picks the first region whose `LANGUAGE_PATTERN` matches the text;
otherwise it falls back to India. It also validates that a region exposes all
required names.

```python
"""Select and validate country-specific worksheet integrations."""

from __future__ import annotations

from types import ModuleType
from typing import Literal

from openpyxl.worksheet.worksheet import Worksheet

from . import china, india


COUNTRY_INTEGRATIONS = (china,)
DEFAULT_INTEGRATION = india
Direction = Literal["IN", "OUT"]


def sheet_text(sheet: Worksheet) -> str:
    values = [sheet.title]
    for row in sheet.iter_rows():
        for cell in row:
            if cell.value is not None:
                values.append(str(cell.value))
    return "\n".join(values)


def integration_for_sheet(sheet: Worksheet) -> ModuleType:
    return integration_for_text(sheet_text(sheet))


def integration_for_text(text: str) -> ModuleType:
    for integration in COUNTRY_INTEGRATIONS:
        if integration.LANGUAGE_PATTERN.search(text):
            validate_integration(integration)
            return integration
    validate_integration(DEFAULT_INTEGRATION)
    return DEFAULT_INTEGRATION


def patterns_for_sheet(sheet: Worksheet, direction: Direction):
    integration = integration_for_sheet(sheet)
    return integration.IN_PATTERNS if direction == "IN" else integration.OUT_PATTERNS


def fallbacks_for_sheet(sheet: Worksheet):
    return integration_for_sheet(sheet).FALLBACKS


def sheet_selection_for_name(sheet_name: str):
    return integration_for_text(sheet_name).SHEET_SELECTION


def validate_integration(integration: ModuleType) -> None:
    required = (
        "COUNTRY_CODE",
        "COUNTRY_NAME",
        "LANGUAGE_PATTERN",
        "SHEET_SELECTION",
        "IN_PATTERNS",
        "OUT_PATTERNS",
        "FALLBACKS",
    )
    missing = [name for name in required if not hasattr(integration, name)]
    if missing:
        raise ValueError(
            f"Country integration {integration.__name__} is missing: {', '.join(missing)}"
        )
```

> **Region detection rule (from TECHNICAL §2):** China is selected if *any* CJK
> character appears in the text; otherwise India. For sheet-level decisions we
> pass just the sheet title; for cell-level extraction we pass the whole sheet's
> text. Because `COUNTRY_INTEGRATIONS = (china,)` is checked first and only India
> is the default, this is exactly "Chinese ⇒ China, else India."

### 6.5 `countries/template.py` (for new regions — see §19)

Copy `template.py` to start a new region. It defines the same dataclasses and
public names with safe never-match placeholders (`(?!x)x`). Fill in the real
regex and register the module in `__init__.py`.

```python
"""Template for a new country integration.

Copy this file, replace the metadata and regex values, then register the module
in countries/__init__.py. Keep the exported names unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Pattern


COUNTRY_CODE = "XX"
COUNTRY_NAME = "Country Name"
LANGUAGE_PATTERN = re.compile(r"(?!x)x")


@dataclass(frozen=True)
class InPatterns:
    container_number: Pattern[str]
    date: Pattern[str]
    time: Pattern[str]


@dataclass(frozen=True)
class OutPatterns:
    container_number: Pattern[str]
    booking_id: Pattern[str]
    vehicle_number: Pattern[str]
    date: Pattern[str]
    time: Pattern[str]


@dataclass(frozen=True)
class Fallbacks:
    date_formats: tuple[str, ...]
    time_formats: tuple[str, ...]
    whitespace_pattern: Pattern[str]
    default_error_code: str
    in_remark_markers: tuple[str, ...]
    out_booking_markers: tuple[str, ...]
    out_booking_fallback: Pattern[str]
    out_seal_markers: tuple[str, ...]
    out_transporter_markers: tuple[str, ...]
    out_remark_markers: tuple[str, ...]
    out_vehicle_markers: tuple[str, ...]


@dataclass(frozen=True)
class SheetSelection:
    standalone_in: Pattern[str]
    standalone_out: Pattern[str]
    gate_in: Pattern[str]
    gate_out: Pattern[str]
    recognized_names: Pattern[str]
    in_language_marker: str
    out_language_marker: str
    excluded_name_parts: tuple[str, ...]
    always_process_names: tuple[str, ...]
    direct_in_names: tuple[str, ...]
    direct_out_names: tuple[str, ...]


SHEET_SELECTION = SheetSelection(
    standalone_in=re.compile(r"(?<![A-Z0-9])IN(?![A-Z0-9])", re.IGNORECASE),
    standalone_out=re.compile(r"(?<![A-Z0-9])OUT(?![A-Z0-9])", re.IGNORECASE),
    gate_in=re.compile(r"GATE\s*IN", re.IGNORECASE),
    gate_out=re.compile(r"GATE\s*OUT", re.IGNORECASE),
    recognized_names=re.compile(
        r"GATE\s*IN|GATE\s*OUT|DAILY\s*MOVEMENT|DAILY\s*REPORT|"
        r"GATE\s*IN\s*&\s*OUT\s*SUMMERY",
        re.IGNORECASE,
    ),
    in_language_marker="",
    out_language_marker="",
    excluded_name_parts=("MONTH", "MASTER"),
    always_process_names=("SHEET1",),
    direct_in_names=(),
    direct_out_names=(),
)


CONTAINER_NUMBER = re.compile(r"\b[A-Z]{3}[UJZ]\d{7}\b", re.IGNORECASE)
DATE_PATTERN = re.compile(r"(?!x)x")
TIME_PATTERN = re.compile(r"(?!x)x")
BOOKING_ID = re.compile(r"(?!x)x")
VEHICLE_NUMBER = re.compile(r"(?!x)x")

IN_PATTERNS = InPatterns(
    container_number=CONTAINER_NUMBER,
    date=DATE_PATTERN,
    time=TIME_PATTERN,
)
OUT_PATTERNS = OutPatterns(
    container_number=CONTAINER_NUMBER,
    booking_id=BOOKING_ID,
    vehicle_number=VEHICLE_NUMBER,
    date=DATE_PATTERN,
    time=TIME_PATTERN,
)

FALLBACKS = Fallbacks(
    date_formats=(),
    time_formats=("%I:%M %p", "%I:%M%p"),
    whitespace_pattern=re.compile(r"\s+"),
    default_error_code="NO_BOOKING_ID",
    in_remark_markers=("remark",),
    out_booking_markers=(),
    out_booking_fallback=re.compile(r"(?!x)x"),
    out_seal_markers=("seal",),
    out_transporter_markers=("transporter",),
    out_remark_markers=("remark",),
    out_vehicle_markers=(),
)
```

---

## 7. `converter.py`

**Purpose:** accept legacy `.xls`/`.xlt` (BIFF) workbooks and convert them to
`.xlsx` so the rest of the pipeline only deals with `.xlsx`. Openpyxl formats
are passed through unchanged.

**Cell-type mapping rules** (xlrd → Python):

- Date cells → `datetime` (using the workbook `datemode`).
- Boolean cells → `bool`.
- Empty/blank cells → `None`.
- Error cells → the error text (`#ERROR!` if unknown).
- Everything else → the raw value.

Merged ranges are re-created on the new sheet. Sheet names are clipped to Excel's
31-character limit.

```python
#!/usr/bin/env python3
"""Convert legacy Excel BIFF workbooks to .xlsx."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import xlrd
from openpyxl import Workbook


LEGACY_EXCEL_SUFFIXES = {".xls", ".xlt"}
OPENXML_EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xltx", ".xltm"}
SUPPORTED_EXCEL_SUFFIXES = LEGACY_EXCEL_SUFFIXES | OPENXML_EXCEL_SUFFIXES


def converted_cell_value(cell: Any, datemode: int) -> Any:
    if cell.ctype == xlrd.XL_CELL_DATE:
        return xlrd.xldate.xldate_as_datetime(cell.value, datemode)
    if cell.ctype == xlrd.XL_CELL_BOOLEAN:
        return bool(cell.value)
    if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
        return None
    if cell.ctype == xlrd.XL_CELL_ERROR:
        return xlrd.error_text_from_code.get(cell.value, "#ERROR!")
    return cell.value


def convert_legacy_workbook(source: Path, target: Path) -> Path:
    source = source.resolve()
    target = target.resolve()
    if source.suffix.lower() not in LEGACY_EXCEL_SUFFIXES:
        raise ValueError(f"Unsupported legacy Excel format: {source.suffix}")

    legacy_book = xlrd.open_workbook(source, formatting_info=True)
    workbook = Workbook()
    workbook.remove(workbook.active)

    for legacy_sheet in legacy_book.sheets():
        sheet = workbook.create_sheet(legacy_sheet.name[:31])
        for row in range(legacy_sheet.nrows):
            for col in range(legacy_sheet.ncols):
                cell = legacy_sheet.cell(row, col)
                sheet.cell(
                    row=row + 1,
                    column=col + 1,
                    value=converted_cell_value(cell, legacy_book.datemode),
                )

        for row_start, row_end, col_start, col_end in legacy_sheet.merged_cells:
            sheet.merge_cells(
                start_row=row_start + 1,
                end_row=row_end,
                start_column=col_start + 1,
                end_column=col_end,
            )

    target.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(target)
    return target


def ensure_xlsx(source: Path, target_dir: Path) -> Path:
    suffix = source.suffix.lower()
    if suffix in OPENXML_EXCEL_SUFFIXES:
        return source
    if suffix in LEGACY_EXCEL_SUFFIXES:
        return convert_legacy_workbook(source, target_dir / f"{source.stem}.xlsx")
    supported = ", ".join(sorted(SUPPORTED_EXCEL_SUFFIXES))
    raise ValueError(f"Unsupported Excel format '{source.suffix}'. Supported: {supported}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a legacy Excel workbook to .xlsx.")
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.workbook.with_suffix(".xlsx")
    print(convert_legacy_workbook(args.workbook, output))


if __name__ == "__main__":
    main()
```

> `xlrd==2.0.2` only reads `.xls`. The note in `xlrd.merged_cells` is that
> end-row/end-col are already exclusive upper bounds, which is why the conversion
> uses `end_row=row_end` (no `+1`) but `start_row=row_start + 1`.

---

## 8. `extract.py`

**Purpose:** the dynamic table detector. No fixed templates. It:

1. Loads the workbook with `data_only=False` (so formulas are *not* mistaken for
   plain-text headers).
2. Builds a **merged-cell map** per sheet.
3. Walks each row into **logical cells** (a horizontal merge = one logical cell;
   skipped duplicate cells inside merges).
4. Detects **header runs** (≥ `min_cells=3` consecutive plain-text cells).
5. Finds an optional **title** above the header (within 2 rows).
6. Reads **data rows** from the row below the header to the first blank row,
   clipped to `[header.start_col, header.end_col]`.
7. Appends a synthetic `Error` column: `INVALID_CONTAINER_NUMBER` when a row has
   no valid container, else `""`.
8. Writes one intermediate `.xlsx` per table under
   `extraction/<workbook>/<sheet>/<title-or-sheet>.xlsx`.

**Sheet selection rules (`should_process_sheet`)** — region-aware via
`sheet_selection_for_name`:

- Reject if the upper-cased name contains any of `excluded_name_parts`
  (`MONTH`, `MASTER`).
- Force-process if the name is in `always_process_names` (`SHEET1`) or in the
  region's `direct_in_names`/`direct_out_names` (China `进场`/`出场`).
- Compute `has_in`/`has_out`: if the region has a language marker present in the
  name use `gate_in`/`gate_out`, otherwise use `standalone_in`/`standalone_out`.
- If the name matches `recognized_names`, process it **unless** it has both IN
  and OUT (ambiguous).
- Otherwise process only when exactly one of IN/OUT is present (XOR).

```python
#!/usr/bin/env python3
"""
Detect spreadsheet headers.

A header is a continuous run on the same row containing at least 3 logical cells.
Each logical cell must contain plain text. A horizontal merged range is treated as
one logical header cell, and its text is extracted from the merged range's
top-left cell.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from converter import ensure_xlsx
from countries import sheet_selection_for_name


CONTAINER_NUMBER = re.compile(r"\b[A-Z]{3}[UJZ]\d{7}\b", re.IGNORECASE)
CSV_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = CSV_ROOT / "processed"
EXTRACTION_DIR = CSV_ROOT / "extraction"


@dataclass(frozen=True)
class LogicalCell:
    row: int
    end_row: int
    start_col: int
    end_col: int
    value: Any
    is_horizontal_merge: bool
    is_vertical_merge: bool


@dataclass(frozen=True)
class ExtractedCell:
    row: int
    end_row: int
    start_col: int
    end_col: int
    value: str
    is_horizontal_merge: bool
    is_vertical_merge: bool


@dataclass(frozen=True)
class TableTitle:
    row: int
    cells: list[ExtractedCell]
    text: str


@dataclass(frozen=True)
class HeaderRun:
    sheet: str
    row: int
    start_col: int
    end_col: int
    logical_cell_count: int
    values: list[str]
    cells: list[ExtractedCell]
    title: TableTitle | None


@dataclass(frozen=True)
class TableExtract:
    index: int
    header: HeaderRun
    data_rows: list[list[ExtractedCell]]
    output: str | None = None


def is_plain_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    return not text.startswith("=")


def merged_cell_map(sheet: Worksheet) -> dict[tuple[int, int], tuple[int, int, int, int, Any]]:
    merge_map: dict[tuple[int, int], tuple[int, int, int, int, Any]] = {}
    for merged_range in sheet.merged_cells.ranges:
        min_col, min_row, max_col, max_row = merged_range.bounds
        value = sheet.cell(row=min_row, column=min_col).value
        for row in range(min_row, max_row + 1):
            for col in range(min_col, max_col + 1):
                merge_map[(row, col)] = (min_col, min_row, max_col, max_row, value)
    return merge_map


def iter_logical_row_cells(
    sheet: Worksheet, row: int, merge_map: dict[tuple[int, int], tuple[int, int, int, int, Any]]
) -> list[LogicalCell]:
    cells: list[LogicalCell] = []
    col = 1
    while col <= sheet.max_column:
        merge = merge_map.get((row, col))
        if merge:
            start_col, start_row, end_col, end_row, value = merge
            if col == start_col:
                cells.append(
                    LogicalCell(
                        row=row,
                        end_row=end_row,
                        start_col=start_col,
                        end_col=end_col,
                        value=value,
                        is_horizontal_merge=end_col > start_col,
                        is_vertical_merge=end_row > start_row,
                    )
                )
            col = end_col + 1
            continue

        cells.append(
            LogicalCell(
                row=row,
                end_row=row,
                start_col=col,
                end_col=col,
                value=sheet.cell(row=row, column=col).value,
                is_horizontal_merge=False,
                is_vertical_merge=False,
            )
        )
        col += 1
    return cells


def detect_headers_in_sheet(sheet: Worksheet, min_cells: int = 3) -> list[HeaderRun]:
    merge_map = merged_cell_map(sheet)
    headers: list[HeaderRun] = []
    row = 1
    while row <= sheet.max_row:
        runs = candidate_header_runs(sheet, row, merge_map, min_cells)
        if not runs:
            row += 1
            continue
        for run in runs:
            headers.append(header_from_run(sheet.title, run, find_title(sheet, row, merge_map)))
        row += 1
        while row <= sheet.max_row and candidate_header_runs(sheet, row, merge_map, min_cells):
            row += 1
    return headers


def candidate_header_runs(
    sheet: Worksheet,
    row: int,
    merge_map: dict[tuple[int, int], tuple[int, int, int, int, Any]],
    min_cells: int,
) -> list[list[LogicalCell]]:
    runs: list[list[LogicalCell]] = []
    run: list[LogicalCell] = []
    for cell in iter_logical_row_cells(sheet, row, merge_map):
        if is_plain_text(cell.value):
            run.append(cell)
            continue
        if len(run) >= min_cells:
            runs.append(run)
        run = []
    if len(run) >= min_cells:
        runs.append(run)
    return runs


def has_content(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def find_title(
    sheet: Worksheet, header_row: int, merge_map: dict[tuple[int, int], tuple[int, int, int, int, Any]]
) -> TableTitle | None:
    for row in range(header_row - 1, max(header_row - 3, 0), -1):
        logical_cells = iter_logical_row_cells(sheet, row, merge_map)
        content_cells = [
            ExtractedCell(
                row=cell.row,
                end_row=cell.end_row,
                start_col=cell.start_col,
                end_col=cell.end_col,
                value=str(cell.value).strip(),
                is_horizontal_merge=cell.is_horizontal_merge,
                is_vertical_merge=cell.is_vertical_merge,
            )
            for cell in logical_cells
            if has_content(cell.value)
        ]
        if content_cells:
            return TableTitle(
                row=row,
                cells=content_cells,
                text=" ".join(cell.value for cell in content_cells),
            )
    return None


def header_from_run(sheet_name: str, run: list[LogicalCell], title: TableTitle | None) -> HeaderRun:
    cells = [
        ExtractedCell(
            row=cell.row,
            end_row=cell.end_row,
            start_col=cell.start_col,
            end_col=cell.end_col,
            value=str(cell.value).strip(),
            is_horizontal_merge=cell.is_horizontal_merge,
            is_vertical_merge=cell.is_vertical_merge,
        )
        for cell in run
    ]
    return HeaderRun(
        sheet=sheet_name,
        row=run[0].row,
        start_col=run[0].start_col,
        end_col=run[-1].end_col,
        logical_cell_count=len(run),
        values=[cell.value for cell in cells],
        cells=cells,
        title=title,
    )


def detect_headers(workbook_path: Path, min_cells: int = 3) -> list[HeaderRun]:
    workbook = load_workbook(workbook_path, data_only=False, read_only=False)
    headers: list[HeaderRun] = []
    for sheet in workbook.worksheets:
        if not should_process_sheet(sheet.title):
            continue
        headers.extend(detect_headers_in_sheet(sheet, min_cells=min_cells))
    return headers


def detect_tables(workbook_path: Path, min_cells: int = 3) -> list[TableExtract]:
    workbook = load_workbook(workbook_path, data_only=False, read_only=False)
    tables: list[TableExtract] = []
    for sheet in workbook.worksheets:
        if not should_process_sheet(sheet.title):
            continue
        merge_map = merged_cell_map(sheet)
        headers = detect_headers_in_sheet(sheet, min_cells=min_cells)
        for header in headers:
            tables.append(
                TableExtract(
                    index=len(tables) + 1,
                    header=header,
                    data_rows=extract_data_rows(sheet, header, merge_map),
                )
            )
    return tables


def prepare_input_workbook(workbook_path: Path) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    source = workbook_path.resolve()
    source = ensure_xlsx(source, PROCESSED_DIR)
    target = PROCESSED_DIR / source.name
    if source == target.resolve():
        return target
    shutil.copy2(source, target)
    return target


def extraction_root_for_workbook(workbook_path: Path) -> Path:
    workbook_folder = sanitize_path_part(workbook_path.stem)
    root = EXTRACTION_DIR / workbook_folder
    root.mkdir(parents=True, exist_ok=True)
    return root


def extract_data_rows(
    sheet: Worksheet,
    header: HeaderRun,
    merge_map: dict[tuple[int, int], tuple[int, int, int, int, Any]],
) -> list[list[ExtractedCell]]:
    rows: list[list[ExtractedCell]] = []
    for row in range(header.row + 1, sheet.max_row + 1):
        logical_cells = iter_logical_row_cells(sheet, row, merge_map)
        if not row_has_content(logical_cells):
            break
        extracted = extract_cells_for_columns(logical_cells, header.start_col, header.end_col)
        extracted.append(
            ExtractedCell(
                row=row,
                end_row=row,
                start_col=header.end_col + 1,
                end_col=header.end_col + 1,
                value="" if row_has_container_number(logical_cells) else "INVALID_CONTAINER_NUMBER",
                is_horizontal_merge=False,
                is_vertical_merge=False,
            )
        )
        rows.append(extracted)
    return rows


def row_has_content(cells: list[LogicalCell]) -> bool:
    return any(has_content(cell.value) for cell in cells)


def row_has_container_number(cells: list[LogicalCell]) -> bool:
    return any(CONTAINER_NUMBER.search(str(cell.value or "")) for cell in cells)


def extract_cells_for_columns(
    cells: list[LogicalCell], start_col: int, end_col: int
) -> list[ExtractedCell]:
    extracted: list[ExtractedCell] = []
    for cell in cells:
        if cell.end_col < start_col or cell.start_col > end_col:
            continue
        extracted.append(
            ExtractedCell(
                row=cell.row,
                end_row=cell.end_row,
                start_col=max(cell.start_col, start_col),
                end_col=min(cell.end_col, end_col),
                value="" if cell.value is None else str(cell.value).strip(),
                is_horizontal_merge=cell.end_col > cell.start_col,
                is_vertical_merge=cell.is_vertical_merge,
            )
        )
    return extracted


def should_process_sheet(sheet_name: str) -> bool:
    selection = sheet_selection_for_name(sheet_name)
    normalized = sheet_name.upper()
    if any(part in normalized for part in selection.excluded_name_parts):
        return False
    if normalized in selection.always_process_names:
        return True
    if normalized in selection.direct_in_names or normalized in selection.direct_out_names:
        return True

    has_in = (
        bool(selection.gate_in.search(sheet_name))
        if selection.in_language_marker and selection.in_language_marker in sheet_name
        else bool(selection.standalone_in.search(sheet_name))
    )
    has_out = (
        bool(selection.gate_out.search(sheet_name))
        if selection.out_language_marker and selection.out_language_marker in sheet_name
        else bool(selection.standalone_out.search(sheet_name))
    )

    if bool(selection.recognized_names.search(sheet_name)):
        return not (has_in and has_out)
    return (has_in or has_out) and not (has_in and has_out)


def write_table_workbooks(tables: list[TableExtract], output_path: Path) -> list[TableExtract]:
    saved_tables: list[TableExtract] = []
    for table in tables:
        sheet_dir = output_path / sanitize_path_part(table.header.sheet)
        sheet_dir.mkdir(parents=True, exist_ok=True)
        table_name = table_filename_stem(table)
        table_path = sheet_dir / f"{table_name}.xlsx"
        saved_path = write_table_workbook(table, table_path)
        saved_tables.append(
            TableExtract(
                index=table.index,
                header=table.header,
                data_rows=table.data_rows,
                output=str(saved_path),
            )
        )
    return saved_tables


def table_filename_stem(table: TableExtract) -> str:
    name = table.header.title.text if table.header.title else table.header.sheet
    return sanitize_path_part(name)[:80] or "table"


def sanitize_path_part(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
    return cleaned or "untitled"


def write_table_workbook(table: TableExtract, output_path: Path) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Table"
    col_offset = table.header.start_col - 1

    if table.header.title:
        write_extracted_cells(sheet, 1, table.header.title.cells, col_offset=col_offset)
        header_output_row = 1 + (table.header.row - table.header.title.row)
    else:
        header_output_row = 1

    write_extracted_cells(sheet, header_output_row, table.header.cells, col_offset=col_offset)
    sheet.cell(
        row=header_output_row,
        column=table.header.end_col - col_offset + 1,
        value="Error",
    )

    current_output_row = header_output_row + 1
    for data_row in table.data_rows:
        write_extracted_cells(sheet, current_output_row, data_row, col_offset=col_offset)
        current_output_row += 1

    saved_path = available_output_path(output_path)
    workbook.save(saved_path)
    return saved_path


def available_output_path(output_path: Path) -> Path:
    if not output_path.exists():
        return output_path
    try:
        with output_path.open("a+b"):
            return output_path
    except PermissionError:
        pass
    for index in range(1, 1000):
        fallback = output_path.with_name(f"{output_path.stem}_{index}{output_path.suffix}")
        if not fallback.exists():
            return fallback
        try:
            with fallback.open("a+b"):
                return fallback
        except PermissionError:
            continue
    raise PermissionError(f"Could not find an unlocked output path near {output_path}")


def write_extracted_cells(
    sheet: Worksheet, output_row: int, cells: list[ExtractedCell], col_offset: int = 0
) -> None:
    for cell in cells:
        output_start_col = max(1, cell.start_col - col_offset)
        output_end_col = max(output_start_col, cell.end_col - col_offset)
        sheet.cell(row=output_row, column=output_start_col, value=cell.value)
        if output_end_col > output_start_col:
            start = get_column_letter(output_start_col)
            end = get_column_letter(output_end_col)
            sheet.merge_cells(f"{start}{output_row}:{end}{output_row}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect text headers in .xlsx sheets.")
    parser.add_argument("workbook", type=Path, help="Path to an Excel workbook")
    parser.add_argument("--output", type=Path, help="Optional extraction root.")
    parser.add_argument("--min-cells", type=int, default=3,
                        help="Minimum logical text cells needed for a header run. Default: 3")
    args = parser.parse_args()

    processed_workbook = prepare_input_workbook(args.workbook)
    output_root = args.output or extraction_root_for_workbook(processed_workbook)
    output_root.mkdir(parents=True, exist_ok=True)
    tables = detect_tables(processed_workbook, min_cells=args.min_cells)
    saved_tables = write_table_workbooks(tables, output_root)

    payload = {
        "processed_workbook": str(processed_workbook),
        "extraction_root": str(output_root),
        "has_tables": bool(saved_tables),
        "outputs": [table.output for table in saved_tables if table.output],
        "tables": [asdict(table) for table in saved_tables],
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
```

> **Why `data_only=False` here but `data_only=True` in `in.py`/`out.py`?**
> During header detection we must *not* let a cached formula result look like a
> plain-text header, so we look at the raw cells and reject anything starting with
> `=`. During field extraction we want the *computed values* (dates, numbers), so
> we open with `data_only=True`.

---

## 9. `movement.py`

**Purpose:** classify each intermediate table as IN or OUT and copy it into
`results/IN/` or `results/OUT/`, naming files after the source workbook.

**Direction logic (`movement_direction`)** for a given string:

- `has_in` = standalone `IN` **or** `GATE IN` **or** Chinese `进`.
- `has_out` = standalone `OUT` **or** `GATE OUT` **or** Chinese `出`.
- Both → `None` (ambiguous). Only IN → `"IN"`. Only OUT → `"OUT"`. Neither → `None`.

**Resolution priority per table file:** filename → parent folder → (final
fallback) original workbook name (using `GATE IN`/`GATE OUT` XOR).

**Suffix rule:** if exactly one direction is found across the whole workbook
folder, append `-IN`/`-OUT` to output names. Deduplicate per `(direction,
basename)` with `_1`, `_2`, …

```python
#!/usr/bin/env python3
"""
Post-process extracted tables.
Categorize tables into IN/OUT master folders and rename them to the source workbook name.
"""

import os
import shutil
import re
from pathlib import Path

CSV_ROOT = Path(__file__).resolve().parents[1]
EXTRACTION_DIR = CSV_ROOT / "extraction"
RESULTS_DIR = CSV_ROOT / "results"

STANDALONE_IN = re.compile(r"(?<![A-Z0-9])IN(?![A-Z0-9])", re.IGNORECASE)
STANDALONE_OUT = re.compile(r"(?<![A-Z0-9])OUT(?![A-Z0-9])", re.IGNORECASE)

CHINESE_IN = "进"   # 进
CHINESE_OUT = "出"  # 出

GATE_IN_RE = re.compile(r"GATE\s*IN", re.IGNORECASE)
GATE_OUT_RE = re.compile(r"GATE\s*OUT", re.IGNORECASE)


def sanitize_path_part(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
    return cleaned or "untitled"


def movement_direction(value: str) -> str | None:
    has_in = bool(STANDALONE_IN.search(value)) or bool(GATE_IN_RE.search(value)) or CHINESE_IN in value
    has_out = bool(STANDALONE_OUT.search(value)) or bool(GATE_OUT_RE.search(value)) or CHINESE_OUT in value
    if has_in and has_out:
        return None
    if has_in:
        return "IN"
    if has_out:
        return "OUT"
    return None


def get_workbook_directions(workbook_dir: Path) -> set[str]:
    directions = set()
    excel_files = list(workbook_dir.rglob("*.xlsx"))
    for f in excel_files:
        direct = movement_direction(f.name)
        if direct is None:
            direct = movement_direction(f.parent.name)
        if direct:
            directions.add(direct)
    return directions


def categorize_and_copy(only_direction: str | None = None):
    if not EXTRACTION_DIR.exists():
        print(f"Extraction directory {EXTRACTION_DIR} does not exist.")
        return

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    copied_counts = {}

    for workbook_dir in EXTRACTION_DIR.iterdir():
        if not workbook_dir.is_dir():
            continue

        workbook_name = workbook_dir.name
        found_dirs = get_workbook_directions(workbook_dir)

        suffix = ""
        if len(found_dirs) == 1:
            suffix = f"-{list(found_dirs)[0]}"

        for root, dirs, files in os.walk(workbook_dir):
            for file in files:
                if not file.lower().endswith(".xlsx"):
                    continue

                table_path = Path(root) / file
                direction = movement_direction(file)
                if direction is None:
                    direction = movement_direction(Path(root).name)
                    if direction is None:
                        has_gate_in = bool(GATE_IN_RE.search(workbook_name))
                        has_gate_out = bool(GATE_OUT_RE.search(workbook_name))
                        if has_gate_in and not has_gate_out:
                            direction = "IN"
                        elif has_gate_out and not has_gate_in:
                            direction = "OUT"

                if direction and (only_direction is None or direction == only_direction):
                    target_dir = RESULTS_DIR / direction
                    target_dir.mkdir(parents=True, exist_ok=True)

                    base_name = sanitize_path_part(workbook_name)
                    final_base = f"{base_name}{suffix}"
                    key = (direction, final_base)

                    if key in copied_counts:
                        copied_counts[key] += 1
                        target_filename = f"{final_base}_{copied_counts[key]}.xlsx"
                    else:
                        copied_counts[key] = 0
                        target_filename = f"{final_base}.xlsx"

                    target_path = target_dir / target_filename
                    shutil.copy2(table_path, target_path)
                    print(f"Copied: {table_path.relative_to(EXTRACTION_DIR)} -> {target_path.relative_to(CSV_ROOT)}")


if __name__ == "__main__":
    categorize_and_copy()
```

> Tables whose direction stays ambiguous (`None`) are **not** copied anywhere, so
> they never reach insertion — exactly the "do not force ambiguous tables" rule.

---

## 10. `db/icms_client.py`

**Purpose:** the only place that talks to SQL Server. Every query runs through
`sqlcmd` as a subprocess via a temp `.sql` file (avoids command-length and
quoting issues). NULLs and separators survive a text round-trip via the `_col()`
projection and a `~NULL~` sentinel.

**Connection settings** (env, seeded from `info.txt`):

- `ICMS_SERVER` (default `10.1.0.6`), `ICMS_DATABASE` (default `ICMS`),
  `ICMS_USER`, `ICMS_PASSWORD`.
- `PROCESS_EMAIL_DATABASE` is the **write** database (inserts + email
  completion).
- Blank user/password ⇒ integrated auth (`-E`).

**Query chunking:** 1000 IDs per `IN (...)`; inserts chunked at 500 rows.

**Status master (from TECHNICAL §55):** IDs 1–15; `RELEVANT_STATUS_IDS = {2,3,6,7}`;
Gate-In valid set is `{2,7}` (enforced in `in.py`).

```python
"""ICMS database client. All access via the sqlcmd CLI (no pyodbc)."""

import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterable

# csv/depot_report/code/db/icms_client.py -> parents[3] == csv root
CSV_ROOT_ENV = Path(__file__).resolve().parents[3]


def _load_env() -> None:
    """Seed os.environ from csv/info.txt without overriding existing variables."""
    env_path = CSV_ROOT_ENV / "info.txt"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_env()

CONTAINER_STATUS_MASTER = {
    1:  "AV",    2:  "EY",   3:  "ECP",  4:  "ECP",  5:  "LIP",
    6:  "LOB",   7:  "LAD",  8:  "EM",   9:  "TLAD", 10: "TLOB",
    11: "LDO",  12: "DM",   13: "VSO",  14: "PO",   15: "DDS",
}
RELEVANT_STATUS_IDS = {2, 3, 6, 7}

_SERVER   = os.environ.get("ICMS_SERVER",   "10.1.0.6")
_DATABASE = os.environ.get("ICMS_DATABASE", "ICMS")
_USER     = os.environ.get("ICMS_USER",     "")
_PASSWORD = os.environ.get("ICMS_PASSWORD", "")
_WRITE_DATABASE = os.environ.get("PROCESS_EMAIL_DATABASE", "EMail_Reader_Process_Data")
_SQLCMD   = os.environ.get("SQLCMD_PATH", "sqlcmd")

_CHUNK = 1000
_INSERT_CHUNK = 500  # SQL Server allows at most 1000 row value expressions
_SEP = "|"
_NULL_TOKEN = "~NULL~"


def _lit(value) -> str:
    """Render a Python value as a T-SQL literal."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, datetime):
        return "'" + value.strftime("%Y-%m-%d %H:%M:%S") + "'"
    return "N'" + str(value).replace("'", "''") + "'"


def _in_list(values: Iterable) -> str:
    return ",".join(_lit(v) for v in values)


def run_sql(sql: str, database: str | None = None) -> list[str]:
    """Execute T-SQL via sqlcmd and return non-empty output lines."""
    script = "SET NOCOUNT ON; SET QUOTED_IDENTIFIER ON; SET XACT_ABORT ON;\n" + sql
    fd, path = tempfile.mkstemp(suffix=".sql", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(script)
        cmd = [_SQLCMD, "-S", _SERVER, "-d", database or _DATABASE]
        if _USER and _PASSWORD:
            cmd += ["-U", _USER, "-P", _PASSWORD]
        else:
            cmd += ["-E"]
        cmd += ["-i", path, "-W", "-h", "-1", "-s", _SEP, "-b", "-l", "30"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"sqlcmd failed (exit {result.returncode}): {detail}")
        return [line for line in result.stdout.splitlines() if line.strip()]
    finally:
        os.unlink(path)


def _query_rows(sql: str, database: str | None = None) -> list[list[str | None]]:
    rows: list[list[str | None]] = []
    for line in run_sql(sql, database=database):
        rows.append([None if part == _NULL_TOKEN else part for part in line.split(_SEP)])
    return rows


def _col(expr: str) -> str:
    """Make a column safe for text transport: cast to NVARCHAR, NULL->sentinel,
    strip the separator character."""
    return (
        f"REPLACE(ISNULL(CAST({expr} AS NVARCHAR(4000)), N'{_NULL_TOKEN}'), N'{_SEP}', N' ')"
    )


def _insert_rows(table_sql: str, rows: list[tuple], database: str) -> int:
    if not rows:
        return 0
    for i in range(0, len(rows), _INSERT_CHUNK):
        chunk = rows[i:i + _INSERT_CHUNK]
        values = ",\n".join("(" + ",".join(_lit(v) for v in row) + ")" for row in chunk)
        run_sql(f"{table_sql} VALUES\n{values};", database=database)
    return len(rows)


# ---------- Inserts (write database) ----------

def insert_gate_in_records(payloads: list[dict]) -> int:
    valid = [
        p["values"] for p in payloads
        if not p["values"].get("ErrorCode") and p["values"].get("PlotID") is not None
    ]
    if not valid:
        return 0
    sql = (
        "INSERT INTO dbo.PlotInDetails ("
        "PlotID, ContainerId, PlotInDate, PlotInStatus, CreatedBy, Remarks, BookingId, EditedBy)"
    )
    params = [
        (v.get("PlotID"), v.get("ContainerId"), v.get("PlotInDate"),
         v.get("PlotInStatus"), 1, v.get("Remarks"), v.get("BookingId"), 1)
        for v in valid
    ]
    return _insert_rows(sql, params, _WRITE_DATABASE)


def insert_gate_out_records(payloads: list[dict]) -> int:
    valid = [
        p["values"] for p in payloads
        if not p["values"].get("ErrorCode") and p["values"].get("PlotId") is not None
    ]
    if not valid:
        return 0
    sql = (
        "INSERT INTO dbo.PlotOutDetails ("
        "BookingId, ContainerId, SealNo, Transporter, VehicleNo, "
        "PlotOutDate, PlotOutTime, Remarks, CreatedBy, PlotOutStatus, PlotId, EditedBy)"
    )
    params = [
        (v.get("BookingId"), v.get("ContainerId"), v.get("SealNo"),
         v.get("Transporter"), v.get("VehicleNo"), v.get("PlotOutDate"),
         v.get("PlotOutTime"), v.get("Remarks"), 1, v.get("PlotOutStatus"),
         v.get("PlotId"), 1)
        for v in valid
    ]
    return _insert_rows(sql, params, _WRITE_DATABASE)


def insert_gate_error_records(payloads: list[dict]) -> int:
    valid = [p["values"] for p in payloads if p.get("values")]
    if not valid:
        return 0
    sql = (
        "INSERT INTO dbo.DepotMovementError ("
        "GateType, ErrorCode, ContainerId, PlotID, PlotInID, PlotOutId, "
        "BookingId, PlotInDate, PlotOutDate, PlotOutTime, PlotInStatus, "
        "PlotOutStatus, OutBookingID, CreatedBy, Remarks, SealNo, "
        "Transporter, VehicleNo, ContType, ContainerStatusId)"
    )
    params = [
        (v.get("GateType"), v.get("ErrorCode"), v.get("ContainerId"),
         v.get("PlotID") or v.get("PlotId"), v.get("PlotInID"), v.get("PlotOutId"),
         v.get("BookingId"), v.get("PlotInDate"), v.get("PlotOutDate"),
         v.get("PlotOutTime"), v.get("PlotInStatus"), v.get("PlotOutStatus"),
         v.get("OutBookingID"), v.get("CreatedBy"), v.get("Remarks"),
         v.get("SealNo"), v.get("Transporter"), v.get("VehicleNo"),
         v.get("ContType"), v.get("ContainerStatusId"))
        for v in valid
    ]
    return _insert_rows(sql, params, _WRITE_DATABASE)


# ---------- Container lookups (read database) ----------

def get_container_status_ids(container_nos: Iterable[str]) -> dict[str, int | None]:
    info = get_container_info(container_nos)
    return {cid: (v[0] if v else None) for cid, v in info.items()}


def get_container_info(container_nos: Iterable[str]) -> dict[str, tuple[int | None, int | None, str] | None]:
    ids = sorted({str(c).strip().upper().replace(" ", "") for c in container_nos if c})
    result: dict[str, tuple[int | None, int | None, str] | None] = {cid: None for cid in ids}
    if not ids:
        return result

    raw: dict[str, tuple[int | None, int | None]] = {}
    plot_ids: set[int] = set()
    for i in range(0, len(ids), _CHUNK):
        chunk = ids[i:i + _CHUNK]
        sql = (
            f"SELECT {_col('ContainerNo')}, {_col('ContainerStatusId')}, {_col('LocationPlotId')} "
            f"FROM ContainerEntry WHERE ContainerNo IN ({_in_list(chunk)});"
        )
        for container_no, status_id, location_plot_id in _query_rows(sql):
            key = str(container_no).strip().upper().replace(" ", "")
            sid_raw = int(status_id) if status_id is not None else None
            sid = sid_raw if sid_raw in RELEVANT_STATUS_IDS else None
            pid = int(location_plot_id) if location_plot_id is not None else None
            raw[key] = (sid, pid)
            if pid is not None:
                plot_ids.add(pid)

    plot_name_by_id: dict[int, str] = {}
    plot_ids_list = sorted(plot_ids)
    for i in range(0, len(plot_ids_list), _CHUNK):
        chunk = plot_ids_list[i:i + _CHUNK]
        sql = (
            f"SELECT {_col('PlotID')}, {_col('PlotName')} FROM PlotInformationDetails "
            f"WHERE PlotID IN ({_in_list(chunk)});"
        )
        for pid, pname in _query_rows(sql):
            plot_name_by_id[int(pid)] = str(pname).strip() if pname is not None else ""

    for cid, (sid, pid) in raw.items():
        result[cid] = (sid, pid, plot_name_by_id.get(pid, "") if pid is not None else "")
    return result


def get_container_ids(container_nos: Iterable[str]) -> dict[str, int | None]:
    ids = sorted({str(c).strip().upper().replace(" ", "") for c in container_nos if c})
    result: dict[str, int | None] = {cid: None for cid in ids}
    if not ids:
        return result
    for i in range(0, len(ids), _CHUNK):
        chunk = ids[i:i + _CHUNK]
        sql = (
            f"SELECT {_col('ContainerNo')}, {_col('ContainerId')} FROM ContainerEntry "
            f"WHERE ContainerNo IN ({_in_list(chunk)});"
        )
        for container_no, container_id in _query_rows(sql):
            key = str(container_no).strip().upper().replace(" ", "")
            result[key] = int(container_id) if container_id is not None else None
    return result


def get_container_types(container_nos: Iterable[str]) -> dict[str, str | None]:
    ids = sorted({str(c).strip().upper().replace(" ", "") for c in container_nos if c})
    result: dict[str, str | None] = {cid: None for cid in ids}
    if not ids:
        return result
    for i in range(0, len(ids), _CHUNK):
        chunk = ids[i:i + _CHUNK]
        sql = (
            f"SELECT {_col('ContainerNo')}, {_col('ContainerType')} FROM ContainerEntry "
            f"WHERE ContainerNo IN ({_in_list(chunk)});"
        )
        for container_no, container_type in _query_rows(sql):
            key = str(container_no).strip().upper().replace(" ", "")
            result[key] = str(container_type).strip() if container_type is not None else None
    return result


def container_ids_exist(container_ids: Iterable[int]) -> dict[int, bool]:
    ids = sorted({int(cid) for cid in container_ids if cid is not None})
    result: dict[int, bool] = {cid: False for cid in ids}
    if not ids:
        return result
    for i in range(0, len(ids), _CHUNK):
        chunk = ids[i:i + _CHUNK]
        sql = (
            f"SELECT {_col('ContainerId')} FROM icms.dbo.ContainerEntry "
            f"WHERE ContainerId IN ({_in_list(chunk)});"
        )
        for (container_id,) in _query_rows(sql):
            result[int(container_id)] = True
    return result


# ---------- Booking lookups ----------

_BOOKED_QTY_PART = re.compile(r"(\d+)\s*X\s*(.+)")


def booking_ids_exist(booking_ids: Iterable[int]) -> dict[int, bool]:
    ids = sorted({int(bid) for bid in booking_ids if bid is not None})
    result: dict[int, bool] = {bid: False for bid in ids}
    if not ids:
        return result
    for i in range(0, len(ids), _CHUNK):
        chunk = ids[i:i + _CHUNK]
        sql = (
            f"SELECT {_col('BookingId')} FROM icms.dbo.BookingDetails "
            f"WHERE BookingId IN ({_in_list(chunk)});"
        )
        for (booking_id,) in _query_rows(sql):
            result[int(booking_id)] = True
    return result


def get_booked_qty_by_booking_id(booking_ids: Iterable[int]) -> dict[int, int]:
    ids = sorted({int(bid) for bid in booking_ids if bid is not None})
    result: dict[int, int] = {bid: 0 for bid in ids}
    if not ids:
        return result
    for i in range(0, len(ids), _CHUNK):
        chunk = ids[i:i + _CHUNK]
        sql = (
            f"SELECT {_col('BookingId')}, {_col('BookedContainerQty')} FROM BookingDetails "
            f"WHERE BookingId IN ({_in_list(chunk)});"
        )
        for booking_id, qty_str in _query_rows(sql):
            total = 0
            if qty_str:
                for part in str(qty_str).split(","):
                    m = _BOOKED_QTY_PART.match(part.strip())
                    if m:
                        total += int(m.group(1))
            result[int(booking_id)] = total
    return result


def get_plotout_container_counts(booking_ids: Iterable[int]) -> dict[int, int]:
    ids = sorted({int(bid) for bid in booking_ids if bid is not None})
    result: dict[int, int] = {bid: 0 for bid in ids}
    if not ids:
        return result
    for i in range(0, len(ids), _CHUNK):
        chunk = ids[i:i + _CHUNK]
        sql = (
            f"SELECT {_col('BookingId')}, {_col('COUNT(ContainerId)')} FROM PlotOutDetails "
            f"WHERE BookingId IN ({_in_list(chunk)}) GROUP BY BookingId;"
        )
        for booking_id, cnt in _query_rows(sql):
            result[int(booking_id)] = int(cnt)
    return result


def _booking_lookup_candidates(value: str) -> list[str]:
    ref = str(value).strip()
    candidates = [ref]
    stripped = re.sub(r"[A-Za-z]+$", "", ref).strip()
    if stripped and stripped != ref:
        candidates.append(stripped)
    return candidates


def get_booking_ids_by_reference(booking_refs: Iterable[str]) -> dict[str, int | None]:
    """Numeric values are already BookingId. Non-numeric values match
    BookingDetails.BookingNo (also trying a trailing-letter-stripped variant)."""
    refs = sorted({str(ref).strip() for ref in booking_refs if str(ref).strip()})
    result: dict[str, int | None] = {}
    lookup_refs: set[str] = set()

    for ref in refs:
        if ref.isdigit():
            result[ref] = int(ref)
        else:
            result[ref] = None
            lookup_refs.update(_booking_lookup_candidates(ref))

    if not lookup_refs:
        return result

    booking_by_no: dict[str, int] = {}
    names = sorted(lookup_refs)
    for i in range(0, len(names), _CHUNK):
        chunk = names[i:i + _CHUNK]
        sql = (
            f"SELECT {_col('BookingNo')}, {_col('BookingId')} FROM BookingDetails "
            f"WHERE BookingNo IN ({_in_list(chunk)});"
        )
        for booking_no, booking_id in _query_rows(sql):
            booking_by_no[str(booking_no).strip()] = int(booking_id)

    for ref in refs:
        if result[ref] is not None:
            continue
        for candidate in _booking_lookup_candidates(ref):
            if candidate in booking_by_no:
                result[ref] = booking_by_no[candidate]
                break
    return result


# ---------- Latest movement ids & previous booking ----------

def get_previous_gate_out_booking_ids(container_ids: Iterable[int]) -> dict[int, int | None]:
    ids = sorted({int(cid) for cid in container_ids if cid is not None})
    result: dict[int, int | None] = {cid: None for cid in ids}
    if not ids:
        return result
    for i in range(0, len(ids), _CHUNK):
        chunk = ids[i:i + _CHUNK]
        sql = f"""
            WITH latest AS (
                SELECT ContainerId, BookingId,
                       ROW_NUMBER() OVER (
                           PARTITION BY ContainerId
                           ORDER BY PlotOutDate DESC, PlotOutId DESC
                       ) AS rn
                FROM PlotOutDetails
                WHERE ContainerId IN ({_in_list(chunk)})
            )
            SELECT {_col('ContainerId')}, {_col('BookingId')} FROM latest WHERE rn = 1;
        """
        for container_id, booking_id in _query_rows(sql):
            result[int(container_id)] = int(booking_id) if booking_id is not None else None
    return result


def get_latest_plot_in_ids_by_status(container_ids: Iterable[int], plot_in_status: str = "P") -> dict[int, int | None]:
    ids = sorted({int(cid) for cid in container_ids if cid is not None})
    result: dict[int, int | None] = {cid: None for cid in ids}
    if not ids:
        return result
    for i in range(0, len(ids), _CHUNK):
        chunk = ids[i:i + _CHUNK]
        sql = f"""
            WITH latest AS (
                SELECT PlotInID, ContainerId,
                       ROW_NUMBER() OVER (
                           PARTITION BY ContainerId
                           ORDER BY PlotInDate DESC, PlotInID DESC
                       ) AS rn
                FROM PlotInDetails
                WHERE PlotInStatus = {_lit(plot_in_status)}
                  AND ContainerId IN ({_in_list(chunk)})
            )
            SELECT {_col('ContainerId')}, {_col('PlotInID')} FROM latest WHERE rn = 1;
        """
        for container_id, plot_in_id in _query_rows(sql):
            result[int(container_id)] = int(plot_in_id) if plot_in_id is not None else None
    return result


def get_latest_plot_out_ids_by_status(container_ids: Iterable[int], plot_out_status: str = "P") -> dict[int, int | None]:
    ids = sorted({int(cid) for cid in container_ids if cid is not None})
    result: dict[int, int | None] = {cid: None for cid in ids}
    if not ids:
        return result
    for i in range(0, len(ids), _CHUNK):
        chunk = ids[i:i + _CHUNK]
        sql = f"""
            WITH latest AS (
                SELECT PlotOutId, ContainerId,
                       ROW_NUMBER() OVER (
                           PARTITION BY ContainerId
                           ORDER BY PlotOutDate DESC, PlotOutId DESC
                       ) AS rn
                FROM PlotOutDetails
                WHERE PlotOutStatus = {_lit(plot_out_status)}
                  AND ContainerId IN ({_in_list(chunk)})
            )
            SELECT {_col('ContainerId')}, {_col('PlotOutId')} FROM latest WHERE rn = 1;
        """
        for container_id, plot_out_id in _query_rows(sql):
            result[int(container_id)] = int(plot_out_id) if plot_out_id is not None else None
    return result


# ---------- Duplicate existence checks ----------

def plotin_records_exist(items: Iterable[tuple[int, str]]) -> set[tuple[int, str]]:
    """Subset of (ContainerId, PlotInDate) already present (PlotInDate as DATE)."""
    pairs = {(int(c), str(d).strip()) for c, d in items if c is not None and d}
    found: set[tuple[int, str]] = set()
    if not pairs:
        return found
    for cid, pdate in pairs:
        sql = (
            f"SELECT {_col('COUNT(*)')} FROM dbo.PlotInDetails "
            f"WHERE ContainerId = {_lit(cid)} AND CAST(PlotInDate AS DATE) = {_lit(pdate)};"
        )
        rows = _query_rows(sql)
        if rows and rows[0][0] is not None and int(rows[0][0]) > 0:
            found.add((cid, pdate))
    return found


def plotout_records_exist(items: Iterable[tuple[int, str, int]]) -> set[tuple[int, str, int]]:
    """Subset of (ContainerId, PlotOutDate, BookingId) already present."""
    triples = {
        (int(c), str(d).strip(), int(b))
        for c, d, b in items
        if c is not None and d and b is not None
    }
    found: set[tuple[int, str, int]] = set()
    if not triples:
        return found
    for cid, pdate, bid in triples:
        sql = (
            f"SELECT {_col('COUNT(*)')} FROM dbo.PlotOutDetails "
            f"WHERE ContainerId = {_lit(cid)} AND CAST(PlotOutDate AS DATE) = {_lit(pdate)} "
            f"AND BookingId = {_lit(bid)};"
        )
        rows = _query_rows(sql)
        if rows and rows[0][0] is not None and int(rows[0][0]) > 0:
            found.add((cid, pdate, bid))
    return found
```

Create `depot_report/code/db/__init__.py` as an **empty file** so `db` is a
package:

```bash
: > depot_report/code/db/__init__.py
```

---

## 11. `in.py`

**Purpose:** for each `.xlsx` under `results/IN/`, extract one Gate-In record per
valid-container row, validate, write `in.txt` and (via `database.py`) the JSON.

**Per-row extraction:**
- First valid container in the row (uppercased). No container ⇒ skip the row.
- First date match in the row → `normalize_date` → `YYYY-MM-DD`.
- First time match in the row → `normalize_time` → `HH:MM:SS.000`.
- Remark from the detected remark column (region markers: India `remark`; China
  also `备注`).

**Validation priority (Gate-In):** `NO_CONTAINER_ID` → `DUPLICATE_RECORD`
(same ContainerId + date already in `PlotInDetails`) → `INVALID_CONTAINER_STATUS_ID`
(status not in `{2,7}`).

```python
#!/usr/bin/env python3
"""Extract IN movement records into one combined text report."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from countries import fallbacks_for_sheet, india, patterns_for_sheet
from database import write_gate_in_payloads
from movement import categorize_and_copy

DEPOT_REPORT_CODE = Path(__file__).resolve().parents[1] / "depot_report" / "code"
sys.path.insert(0, str(DEPOT_REPORT_CODE))
from db.icms_client import get_container_ids, get_container_info, plotin_records_exist


CSV_ROOT = Path(__file__).resolve().parents[1]
IN_DIR = CSV_ROOT / "results" / "IN"
OUTPUT_PATH = CSV_ROOT / "results" / "in.txt"
SEP = " | "


@dataclass(frozen=True)
class Record:
    container_no: str
    date: str
    time: str
    remark: str
    container_status: str = ""
    error_code: str = ""


def merged_cell_map(sheet: Worksheet) -> dict[tuple[int, int], tuple[int, int, int, int, Any]]:
    merge_map: dict[tuple[int, int], tuple[int, int, int, int, Any]] = {}
    for merged_range in sheet.merged_cells.ranges:
        min_col, min_row, max_col, max_row = merged_range.bounds
        value = sheet.cell(row=min_row, column=min_col).value
        for row in range(min_row, max_row + 1):
            for col in range(min_col, max_col + 1):
                merge_map[(row, col)] = (min_col, min_row, max_col, max_row, value)
    return merge_map


def cell_value(sheet, row, col, merge_map) -> Any:
    merge = merge_map.get((row, col))
    if merge:
        start_col, start_row, _ec, _er, value = merge
        if row == start_row and col == start_col:
            return value
        return None
    return sheet.cell(row=row, column=col).value


def display_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    return " ".join(str(value).strip().split())


def find_remark_column(sheet, merge_map, markers: tuple[str, ...]) -> int | None:
    for row in range(1, sheet.max_row + 1):
        for col in range(1, sheet.max_column + 1):
            value = display_value(cell_value(sheet, row, col, merge_map)).lower()
            if any(marker.lower() in value for marker in markers):
                return col
    return None


def first_container(values, pattern: re.Pattern[str] = india.IN_PATTERNS.container_number) -> str | None:
    for value in values:
        match = pattern.search(str(value or "").strip())
        if match:
            return match.group(0).upper()
    return None


def first_match(values, pattern: re.Pattern) -> Any:
    for value in values:
        if pattern.search(str(value or "").strip()):
            return value
    return None


def normalize_date(value, pattern=india.IN_PATTERNS.date,
                   formats=india.FALLBACKS.date_formats,
                   whitespace_pattern=india.FALLBACKS.whitespace_pattern) -> str:
    if isinstance(value, datetime) or isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    text = str(value or "").strip()
    match = pattern.search(text)
    if not match:
        return text
    raw = match.group(0).replace(",", " ")
    raw = whitespace_pattern.sub(" ", raw).strip()
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw


def normalize_time(value, pattern=india.IN_PATTERNS.time, formats=india.FALLBACKS.time_formats) -> str:
    if isinstance(value, datetime) or isinstance(value, time):
        return value.strftime("%H:%M:%S.000")
    text = str(value or "").strip()
    match = pattern.search(text)
    if not match:
        return text
    raw_time = match.group(0)
    for fmt in formats:
        try:
            return datetime.strptime(raw_time, fmt).strftime("%H:%M:%S.000")
        except ValueError:
            continue
    hour, minute, second, _ = match.groups()
    return f"{int(hour):02d}:{minute}:{second or '00'}.000"


def extract_records(workbook_path: Path) -> list[Record]:
    workbook = load_workbook(workbook_path, data_only=True, read_only=False)
    records: list[Record] = []
    try:
        for sheet in workbook.worksheets:
            patterns = patterns_for_sheet(sheet, "IN")
            fallbacks = fallbacks_for_sheet(sheet)
            merge_map = merged_cell_map(sheet)
            remark_col = find_remark_column(sheet, merge_map, fallbacks.in_remark_markers)
            for row in range(1, sheet.max_row + 1):
                raw_values = [cell_value(sheet, row, col, merge_map) for col in range(1, sheet.max_column + 1)]
                container_no = first_container(raw_values, patterns.container_number)
                if not container_no:
                    continue
                remark = ""
                if remark_col is not None:
                    remark = display_value(cell_value(sheet, row, remark_col, merge_map))
                records.append(Record(
                    container_no=container_no,
                    date=normalize_date(first_match(raw_values, patterns.date),
                                        patterns.date, fallbacks.date_formats, fallbacks.whitespace_pattern),
                    time=normalize_time(first_match(raw_values, patterns.time),
                                        patterns.time, fallbacks.time_formats),
                    remark=remark,
                ))
    finally:
        workbook.close()
    return validate_records(records)


def validate_records(records: list[Record]) -> list[Record]:
    container_ids = get_container_ids(record.container_no for record in records)
    container_info = get_container_info(record.container_no for record in records)
    duplicate_pairs = [
        (container_ids.get(record.container_no), record.date)
        for record in records
        if container_ids.get(record.container_no) is not None and record.date
    ]
    duplicates = plotin_records_exist(duplicate_pairs)
    validated: list[Record] = []

    for record in records:
        container_id = container_ids.get(record.container_no)
        info = container_info.get(record.container_no)
        status_id = info[0] if info is not None else None
        error_code = ""
        if container_id is None:
            error_code = "NO_CONTAINER_ID"
        elif record.date and (int(container_id), record.date) in duplicates:
            error_code = "DUPLICATE_RECORD"
        elif status_id not in (2, 7):
            error_code = "INVALID_CONTAINER_STATUS_ID"
        validated.append(Record(
            container_no=record.container_no,
            date=record.date,
            time=record.time,
            remark=record.remark,
            container_status="" if status_id is None else str(status_id),
            error_code=error_code,
        ))
    return validated


def table_lines(title: str, records: list[Record]) -> list[str]:
    headers = ["Container #", "Date", "Time", "Remark", "Cnt_status", "ErrorCode"]
    rows = [headers]
    rows.extend([[r.container_no, r.date, r.time, r.remark, r.container_status, r.error_code] for r in records])
    widths = [max(len(row[i]) for row in rows) for i in range(len(headers))]
    lines = [title]
    lines.append(SEP.join(v.ljust(widths[i]) for i, v in enumerate(rows[0])))
    lines.append(SEP.join("-" * w for w in widths))
    for row in rows[1:]:
        lines.append(SEP.join(v.ljust(widths[i]) for i, v in enumerate(row)))
    if not records:
        lines.append("(none)")
    return lines


def build_report(input_dir: Path | None = None, output_path: Path | None = None, synchronize: bool = True) -> Path:
    input_dir = input_dir or IN_DIR
    output_path = output_path or OUTPUT_PATH
    if synchronize and input_dir == IN_DIR:
        categorize_and_copy(only_direction="IN")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    records_by_depot: list[tuple[str, list[Record]]] = []
    for workbook_path in sorted(input_dir.glob("*.xlsx")):
        try:
            records = extract_records(workbook_path)
        except Exception as exc:
            print(f"IN extract failed for {workbook_path.name}: {exc}")
            records = []
        records_by_depot.append((workbook_path.stem, records))
        if lines:
            lines.append("")
        lines.extend(table_lines(workbook_path.stem, records))
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_gate_in_payloads(records_by_depot)
    return output_path


def main() -> None:
    print(build_report())


if __name__ == "__main__":
    main()
```

> The default-argument patterns (`india.IN_PATTERNS...`) are only fallbacks; in
> the real loop the **region-specific** `patterns`/`fallbacks` for each sheet are
> always passed in explicitly.

---

## 12. `out.py`

**Purpose:** for each `.xlsx` under `results/OUT/`, extract one Gate-Out record
per valid-container row, resolve booking/seal/transporter/vehicle/remarks
columns, take the **last/rightmost** date & time in the row, validate, write
`out.txt` and JSON.

**Booking column resolution (priority):**
1. Rightmost column matching the strict booking regex `XXX/XXX/######`.
2. Region booking markers (China `单号`).
3. Region booking fallback regex (India never-match `(?!x)x`; China `^\d{6}$`).

Booking value error during extraction: if it matches the booking regex **or** the
region fallback, error is empty; otherwise set `default_error_code`
(`NO_BOOKING_ID`). This `NO_BOOKING_ID` is **preserved** through validation.

**Vehicle column:** region vehicle markers first (China `场车牌`); if none, scan
container rows for a vehicle-regex match (India plate / China province plate).

**Validation priority (Gate-Out):** preserve prior `NO_BOOKING_ID` →
`NO_CONTAINER_ID` → `DUPLICATE_RECORD` (ContainerId + date + BookingId) →
`INVALID_ECP_COUNT` (extracted qty for booking exceeds `booked − already
plotted`).

```python
#!/usr/bin/env python3
"""Extract OUT movement records into one combined text report."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from countries import fallbacks_for_sheet, india, patterns_for_sheet
from database import write_gate_out_payloads
from movement import categorize_and_copy

DEPOT_REPORT_CODE = Path(__file__).resolve().parents[1] / "depot_report" / "code"
sys.path.insert(0, str(DEPOT_REPORT_CODE))
from db.icms_client import (
    get_booked_qty_by_booking_id,
    get_booking_ids_by_reference,
    get_container_ids,
    get_plotout_container_counts,
    plotout_records_exist,
)


CSV_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = CSV_ROOT / "results" / "OUT"
OUTPUT_PATH = CSV_ROOT / "results" / "out.txt"
SEP = " | "


@dataclass(frozen=True)
class Record:
    container_id: str
    booking_id: str
    seal_no: str
    plot_out_date: str
    plot_out_time: str
    transporter: str
    vehicle_no: str
    remarks: str
    error_code: str


def merged_cell_map(sheet: Worksheet) -> dict[tuple[int, int], tuple[int, int, int, int, Any]]:
    merge_map: dict[tuple[int, int], tuple[int, int, int, int, Any]] = {}
    for merged_range in sheet.merged_cells.ranges:
        min_col, min_row, max_col, max_row = merged_range.bounds
        value = sheet.cell(row=min_row, column=min_col).value
        for row in range(min_row, max_row + 1):
            for col in range(min_col, max_col + 1):
                merge_map[(row, col)] = (min_col, min_row, max_col, max_row, value)
    return merge_map


def cell_value(sheet, row, col, merge_map) -> Any:
    if col is None:
        return None
    merge = merge_map.get((row, col))
    if merge:
        start_col, start_row, _ec, _er, value = merge
        if row == start_row and col == start_col:
            return value
        return None
    return sheet.cell(row=row, column=col).value


def display_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    return " ".join(str(value).strip().split())


def find_header_column(sheet, merge_map, needle: str) -> int | None:
    needle = needle.lower()
    rightmost = None
    for row in range(1, sheet.max_row + 1):
        for col in range(1, sheet.max_column + 1):
            if needle in display_value(cell_value(sheet, row, col, merge_map)).lower():
                if rightmost is None or col > rightmost:
                    rightmost = col
    return rightmost


def find_header_column_for_markers(sheet, merge_map, markers: tuple[str, ...]) -> int | None:
    matches = [
        column
        for marker in markers
        if (column := find_header_column(sheet, merge_map, marker)) is not None
    ]
    return max(matches) if matches else None


def first_container(values, pattern: re.Pattern[str] = india.OUT_PATTERNS.container_number) -> str | None:
    for value in values:
        match = pattern.search(str(value or "").strip())
        if match:
            return match.group(0).upper()
    return None


def last_match(values, pattern: re.Pattern) -> Any:
    for value in reversed(values):
        if pattern.search(str(value or "").strip()):
            return value
    return None


def find_regex_column(sheet, pattern: re.Pattern[str]) -> int | None:
    matches: list[int] = []
    for row in range(1, sheet.max_row + 1):
        for col in range(1, sheet.max_column + 1):
            val = sheet.cell(row=row, column=col).value
            if pattern.search(str(val or "").strip()):
                matches.append(col)
    return max(matches) if matches else None


def normalize_date(value, pattern=india.OUT_PATTERNS.date,
                   formats=india.FALLBACKS.date_formats,
                   whitespace_pattern=india.FALLBACKS.whitespace_pattern) -> str:
    if isinstance(value, datetime) or isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    text = str(value or "").strip()
    match = pattern.search(text)
    if not match:
        return text
    raw = match.group(0).replace(",", " ")
    raw = whitespace_pattern.sub(" ", raw).strip()
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw


def normalize_time(value, pattern=india.OUT_PATTERNS.time, formats=india.FALLBACKS.time_formats) -> str:
    if isinstance(value, datetime) or isinstance(value, time):
        return value.strftime("%H:%M:%S.000")
    text = str(value or "").strip()
    match = pattern.search(text)
    if not match:
        return text
    raw_time = match.group(0)
    for fmt in formats:
        try:
            return datetime.strptime(raw_time, fmt).strftime("%H:%M:%S.000")
        except ValueError:
            continue
    hour, minute, second, _ = match.groups()
    return f"{int(hour):02d}:{minute}:{second or '00'}.000"


def extract_records(workbook_path: Path) -> list[Record]:
    workbook = load_workbook(workbook_path, data_only=True, read_only=False)
    records: list[Record] = []
    try:
        for sheet in workbook.worksheets:
            patterns = patterns_for_sheet(sheet, "OUT")
            fallbacks = fallbacks_for_sheet(sheet)
            merge_map = merged_cell_map(sheet)

            # Booking ID: Regex -> Marker -> region fallback
            booking_col = find_regex_column(sheet, patterns.booking_id)
            if not booking_col:
                booking_col = find_header_column_for_markers(sheet, merge_map, fallbacks.out_booking_markers)
            if not booking_col:
                booking_col = find_regex_column(sheet, fallbacks.out_booking_fallback)

            seal_col = find_header_column_for_markers(sheet, merge_map, fallbacks.out_seal_markers)
            transporter_col = find_header_column_for_markers(sheet, merge_map, fallbacks.out_transporter_markers)
            remarks_col = find_header_column_for_markers(sheet, merge_map, fallbacks.out_remark_markers)
            vehicle_col = find_header_column_for_markers(sheet, merge_map, fallbacks.out_vehicle_markers)

            if not vehicle_col:
                representative_rows = []
                for row in range(1, sheet.max_row + 1):
                    vals = [cell_value(sheet, row, col, merge_map) for col in range(1, sheet.max_column + 1)]
                    if first_container(vals, patterns.container_number):
                        representative_rows.append(row)
                for row in representative_rows:
                    for col in range(1, sheet.max_column + 1):
                        val = str(cell_value(sheet, row, col, merge_map) or "")
                        if patterns.vehicle_number.search(val):
                            vehicle_col = col
                            break
                    if vehicle_col:
                        break

            for row in range(1, sheet.max_row + 1):
                raw_values = [cell_value(sheet, row, col, merge_map) for col in range(1, sheet.max_column + 1)]
                container_id = first_container(raw_values, patterns.container_number)
                if not container_id:
                    continue
                booking_id = display_value(cell_value(sheet, row, booking_col, merge_map))
                error_code = (
                    ""
                    if (patterns.booking_id.search(booking_id) or fallbacks.out_booking_fallback.search(booking_id))
                    else fallbacks.default_error_code
                )
                records.append(Record(
                    container_id=container_id,
                    booking_id=booking_id,
                    seal_no=display_value(cell_value(sheet, row, seal_col, merge_map)),
                    plot_out_date=normalize_date(last_match(raw_values, patterns.date),
                                                 patterns.date, fallbacks.date_formats, fallbacks.whitespace_pattern),
                    plot_out_time=normalize_time(last_match(raw_values, patterns.time),
                                                 patterns.time, fallbacks.time_formats),
                    transporter=display_value(cell_value(sheet, row, transporter_col, merge_map)),
                    vehicle_no=display_value(cell_value(sheet, row, vehicle_col, merge_map)),
                    remarks=display_value(cell_value(sheet, row, remarks_col, merge_map)),
                    error_code=error_code,
                ))
    finally:
        workbook.close()
    return validate_records(records)


def validate_records(records: list[Record]) -> list[Record]:
    container_ids = get_container_ids(record.container_id for record in records)
    booking_refs = [record.booking_id for record in records if record.booking_id]
    booking_ids = get_booking_ids_by_reference(booking_refs)

    duplicate_keys: list[tuple[int, str, int] | None] = []
    duplicate_candidates: list[tuple[int, str, int]] = []
    for record in records:
        container_id = container_ids.get(record.container_id)
        booking_id = booking_ids.get(record.booking_id) if record.booking_id else None
        if container_id is not None and booking_id is not None and record.plot_out_date:
            key = (int(container_id), record.plot_out_date, int(booking_id))
            duplicate_keys.append(key)
            duplicate_candidates.append(key)
        else:
            duplicate_keys.append(None)
    duplicates = plotout_records_exist(duplicate_candidates)

    eligible_booking_ids: list[int | None] = []
    extracted_counts: dict[int, int] = {}
    for record, duplicate_key in zip(records, duplicate_keys):
        container_id = container_ids.get(record.container_id)
        booking_id = booking_ids.get(record.booking_id) if record.booking_id else None
        has_prior_error = bool(record.error_code)
        is_duplicate = duplicate_key is not None and duplicate_key in duplicates
        if container_id is not None and booking_id is not None and not has_prior_error and not is_duplicate:
            extracted_counts[booking_id] = extracted_counts.get(booking_id, 0) + 1
            eligible_booking_ids.append(booking_id)
        else:
            eligible_booking_ids.append(None)

    booked = get_booked_qty_by_booking_id(extracted_counts)
    existing = get_plotout_container_counts(extracted_counts)
    invalid_ecp = {
        booking_id
        for booking_id, extracted in extracted_counts.items()
        if extracted > booked.get(booking_id, 0) - existing.get(booking_id, 0)
    }

    validated: list[Record] = []
    for record, duplicate_key, booking_id in zip(records, duplicate_keys, eligible_booking_ids):
        error_code = record.error_code
        if container_ids.get(record.container_id) is None:
            error_code = "NO_CONTAINER_ID"
        elif not error_code and duplicate_key is not None and duplicate_key in duplicates:
            error_code = "DUPLICATE_RECORD"
        elif not error_code and booking_id in invalid_ecp:
            error_code = "INVALID_ECP_COUNT"
        validated.append(Record(
            container_id=record.container_id,
            booking_id=record.booking_id,
            seal_no=record.seal_no,
            plot_out_date=record.plot_out_date,
            plot_out_time=record.plot_out_time,
            transporter=record.transporter,
            vehicle_no=record.vehicle_no,
            remarks=record.remarks,
            error_code=error_code,
        ))
    return validated


def table_lines(title: str, records: list[Record]) -> list[str]:
    headers = ["ContainerID", "BookingId", "SealNo", "PlotOutDate", "PlotOutTime",
               "Transporter", "VehicleNo", "Remarks", "ErrorCode"]
    rows = [headers]
    rows.extend([[r.container_id, r.booking_id, r.seal_no, r.plot_out_date, r.plot_out_time,
                  r.transporter, r.vehicle_no, r.remarks, r.error_code] for r in records])
    widths = [max(len(row[i]) for row in rows) for i in range(len(headers))]
    lines = [title]
    lines.append(SEP.join(v.ljust(widths[i]) for i, v in enumerate(rows[0])))
    lines.append(SEP.join("-" * w for w in widths))
    for row in rows[1:]:
        lines.append(SEP.join(v.ljust(widths[i]) for i, v in enumerate(row)))
    if not records:
        lines.append("(none)")
    return lines


def build_report(input_dir: Path | None = None, output_path: Path | None = None, synchronize: bool = True) -> Path:
    input_dir = input_dir or OUT_DIR
    output_path = output_path or OUTPUT_PATH
    if synchronize and input_dir == OUT_DIR:
        categorize_and_copy(only_direction="OUT")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    records_by_depot: list[tuple[str, list[Record]]] = []
    for workbook_path in sorted(input_dir.glob("*.xlsx")):
        try:
            records = extract_records(workbook_path)
        except Exception as exc:
            print(f"OUT extract failed for {workbook_path.name}: {exc}")
            records = []
        records_by_depot.append((workbook_path.stem, records))
        if lines:
            lines.append("")
        lines.extend(table_lines(workbook_path.stem, records))
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_gate_out_payloads(records_by_depot)
    return output_path


def main() -> None:
    print(build_report())


if __name__ == "__main__":
    main()
```

---

## 13. `database.py`

**Purpose:** turn validated records into JSON payloads (`gate_in.json`,
`gate_out.json`), build the error output (`gate_errors.json`), optionally insert
everything, and write back email completion.

**PlotID derivation:** the depot label is the workbook stem (e.g. `123_1`); the
plot id is the integer prefix before the first underscore (`123`).

**Error output rule:** include any record with an `ErrorCode` **except**
`DUPLICATE_RECORD` (duplicates are treated as already-existing, not actionable);
tag each with `GateType` `IN`/`OUT`.

```python
#!/usr/bin/env python3
"""Build and publish gate-movement JSON payloads from extracted records."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

DEPOT_REPORT_CODE = Path(__file__).resolve().parents[1] / "depot_report" / "code"
sys.path.insert(0, str(DEPOT_REPORT_CODE))

from db.icms_client import (  # noqa: E402
    run_sql,
    get_booking_ids_by_reference,
    get_container_ids,
    get_container_status_ids,
    get_container_types,
    get_latest_plot_in_ids_by_status,
    get_latest_plot_out_ids_by_status,
    get_previous_gate_out_booking_ids,
    insert_gate_error_records,
    insert_gate_in_records,
    insert_gate_out_records,
)


CSV_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = CSV_ROOT / "results"
GATE_IN_JSON = RESULTS_DIR / "gate_in.json"
GATE_OUT_JSON = RESULTS_DIR / "gate_out.json"
GATE_ERRORS_JSON = RESULTS_DIR / "gate_errors.json"
PROCESS_EMAIL_DATABASE = os.environ.get("PROCESS_EMAIL_DATABASE", "EMail_Reader_Process_Data")


def _sql_str(value: str) -> str:
    return "N'" + str(value).replace("'", "''") + "'"


def mark_process_emails_completed(internet_message_ids: Iterable[str], completed_at: datetime) -> int:
    message_ids = sorted({str(m).strip() for m in internet_message_ids if str(m).strip()})
    if not message_ids:
        return 0
    completed_literal = "'" + completed_at.strftime("%Y-%m-%d %H:%M:%S") + "'"
    id_list = ",".join(_sql_str(m) for m in message_ids)
    sql = f"""
        UPDATE dbo.tbl_Process_Emails
        SET completed_at = {completed_literal}
        WHERE internet_message_id IN ({id_list})
          AND completed_at IS NULL;
        SELECT @@ROWCOUNT;
    """
    lines = run_sql(sql, database=PROCESS_EMAIL_DATABASE)
    return int(lines[-1].strip()) if lines else 0


def _value(record: Any, name: str, default: Any = None) -> Any:
    return getattr(record, name, default)


def _blank_to_none(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def plot_id_from_attachment_name(name: str) -> int | None:
    stem = Path(str(name).strip()).stem
    plot_id = stem.split("_", 1)[0].strip()
    return int(plot_id) if plot_id.isdigit() else None


def _write_json(path: Path, payloads: list[dict[str, dict[str, Any]]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payloads, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _read_json(path: Path) -> list[dict[str, dict[str, Any]]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def build_gate_in_payloads(records_by_depot: Iterable[tuple[str, Iterable[Any]]]) -> list[dict[str, dict[str, Any]]]:
    rows = [(depot, record) for depot, records in records_by_depot for record in records]
    container_ids = get_container_ids(_value(record, "container_no") for _depot, record in rows)
    internal_ids = [cid for cid in container_ids.values() if cid is not None]
    booking_ids = get_previous_gate_out_booking_ids(internal_ids)
    plot_in_ids = get_latest_plot_in_ids_by_status(internal_ids)

    payloads: list[dict[str, dict[str, Any]]] = []
    for depot, record in rows:
        container_no = _value(record, "container_no")
        container_id = container_ids.get(container_no)
        values = {
            "PlotInID": plot_in_ids.get(container_id) if container_id else None,
            "PlotID": plot_id_from_attachment_name(depot),
            "ContainerId": container_id,
            "PlotInDate": _blank_to_none(_value(record, "date")),
            "PlotInStatus": "P",
            "CreatedBy": 1,
            "Remarks": _blank_to_none(_value(record, "remark")),
            "BookingId": booking_ids.get(container_id) if container_id else None,
            "OutBookingID": None,
            "ContainerStatusId": _blank_to_none(_value(record, "container_status")),
        }
        error_code = _blank_to_none(_value(record, "error_code"))
        if error_code:
            values["ErrorCode"] = error_code
        payloads.append({"values": values})
    return payloads


def build_gate_out_payloads(records_by_depot: Iterable[tuple[str, Iterable[Any]]]) -> list[dict[str, dict[str, Any]]]:
    rows = [(depot, record) for depot, records in records_by_depot for record in records]
    container_nos = [_value(record, "container_id") for _depot, record in rows]
    container_ids = get_container_ids(container_nos)
    internal_ids = [cid for cid in container_ids.values() if cid is not None]
    booking_refs = [
        _value(record, "booking_id")
        for _depot, record in rows
        if _blank_to_none(_value(record, "booking_id"))
    ]
    booking_ids = get_booking_ids_by_reference(booking_refs)
    container_types = get_container_types(container_nos)
    status_ids = get_container_status_ids(container_nos)
    plot_out_ids = get_latest_plot_out_ids_by_status(internal_ids)

    payloads: list[dict[str, dict[str, Any]]] = []
    for depot, record in rows:
        container_no = _value(record, "container_id")
        container_id = container_ids.get(container_no)
        booking_ref = _blank_to_none(_value(record, "booking_id"))
        values = {
            "PlotOutId": plot_out_ids.get(container_id) if container_id else None,
            "BookingId": booking_ref,
            "ContainerId": container_id,
            "SealNo": _blank_to_none(_value(record, "seal_no")),
            "Transporter": _blank_to_none(_value(record, "transporter")),
            "VehicleNo": _blank_to_none(_value(record, "vehicle_no")),
            "PlotOutDate": _blank_to_none(_value(record, "plot_out_date")),
            "PlotOutTime": _blank_to_none(_value(record, "plot_out_time")),
            "Remarks": _blank_to_none(_value(record, "remarks")),
            "CreatedBy": 1,
            "PlotOutStatus": "P",
            "PlotId": plot_id_from_attachment_name(depot),
            "ContType": container_types.get(container_no),
            "ContainerStatusId": status_ids.get(container_no),
        }
        error_code = _blank_to_none(_value(record, "error_code"))
        if error_code:
            values["ErrorCode"] = error_code
        payloads.append({"values": values})
    return payloads


def build_error_payloads(gate_in_payloads, gate_out_payloads) -> list[dict[str, dict[str, Any]]]:
    errors: list[dict[str, dict[str, Any]]] = []
    for gate_type, payloads in (("IN", gate_in_payloads), ("OUT", gate_out_payloads)):
        for payload in payloads:
            values = payload.get("values", {})
            error_codes = {c.strip() for c in str(values.get("ErrorCode") or "").split(",") if c.strip()}
            if not error_codes or "DUPLICATE_RECORD" in error_codes:
                continue
            error_values = dict(values)
            error_values["GateType"] = gate_type
            errors.append({"values": error_values})
    return errors


def refresh_error_output() -> Path:
    errors = build_error_payloads(_read_json(GATE_IN_JSON), _read_json(GATE_OUT_JSON))
    return _write_json(GATE_ERRORS_JSON, errors)


def reset_generated_payloads() -> None:
    for path in (GATE_IN_JSON, GATE_OUT_JSON, GATE_ERRORS_JSON):
        if path.exists():
            path.unlink()


def write_gate_in_payloads(records_by_depot):
    payloads = build_gate_in_payloads(records_by_depot)
    path = _write_json(GATE_IN_JSON, payloads)
    refresh_error_output()
    return path, payloads


def write_gate_out_payloads(records_by_depot):
    payloads = build_gate_out_payloads(records_by_depot)
    path = _write_json(GATE_OUT_JSON, payloads)
    refresh_error_output()
    return path, payloads


def insert_generated_payloads() -> dict[str, int]:
    gate_in = _read_json(GATE_IN_JSON)
    gate_out = _read_json(GATE_OUT_JSON)
    errors = build_error_payloads(gate_in, gate_out)
    _write_json(GATE_ERRORS_JSON, errors)
    return {
        "gate_in_inserted": insert_gate_in_records(gate_in),
        "gate_out_inserted": insert_gate_out_records(gate_out),
        "gate_errors_inserted": insert_gate_error_records(errors),
    }
```

---

## 14. `pipeline.py`

**Purpose:** the single command operators run. It:

1. Creates an isolated temp run under `files/.running/<uuid>/`.
2. Repoints every module's module-level path constants at that run
   (`configure_run_paths`).
3. Resets old JSON, discovers workbooks, captures email message IDs.
4. For each workbook: convert/prepare → detect tables → write intermediate tables.
   A single bad workbook is caught and recorded; it never aborts the batch.
5. Categorizes IN/OUT, builds `in.txt`/`out.txt` + JSON, optionally inserts.
6. Archives the inputs that came from `files/api/`.
7. **Atomically** publishes `processed`, `extraction`, `results` under a
   timestamped folder (`os.replace`), removes the temp run.
8. Returns a JSON run summary.

```python
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
    for name, root in (("processed", PROCESSED_ROOT), ("extraction", EXTRACTION_ROOT), ("results", RESULTS_ROOT)):
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
            if (candidate.is_file()
                    and not candidate.name.startswith("~$")
                    and candidate.suffix.lower() in SUPPORTED_EXCEL_SUFFIXES):
                workbooks[candidate.resolve()] = None
    if not workbooks:
        raise ValueError("No supported Excel workbooks were found.")
    return sorted(workbooks, key=lambda path: str(path).lower())


def run_pipeline(inputs: list[Path], min_cells: int = 3, insert_database: bool = False) -> dict[str, object]:
    FILES_ROOT.mkdir(parents=True, exist_ok=True)
    run_root = FILES_ROOT / ".running" / uuid.uuid4().hex
    try:
        return _run_pipeline_inner(inputs, run_root, min_cells=min_cells, insert_database=insert_database)
    except Exception:
        shutil.rmtree(run_root, ignore_errors=True)
        raise


def _run_pipeline_inner(inputs: list[Path], run_root: Path, min_cells: int = 3, insert_database: bool = False) -> dict[str, object]:
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
            workbook_results.append({
                "source": str(source),
                "processed": str(processed),
                "extraction_root": str(extraction_root),
                "outputs": [table.output for table in saved_tables if table.output],
            })
        except Exception as exc:
            workbook_results.append({"source": str(source), "error": str(exc)})

    with redirect_stdout(io.StringIO()):
        movement.categorize_and_copy()
    in_report.build_report(synchronize=False)
    out.build_report(synchronize=False)
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
        if insert_database else 0
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
    parser.add_argument("inputs", nargs="*", type=Path,
                        help="Excel files/folders. Default: files/api relative to the csv root")
    parser.add_argument("--min-cells", type=int, default=3,
                        help="Minimum logical text cells needed for a header run. Default: 3")
    parser.add_argument("--insert", action="store_true",
                        help="Insert valid movement payloads and error payloads into the process database.")
    args = parser.parse_args()
    inputs = args.inputs or [API_DIR]
    print(json.dumps(run_pipeline(inputs, min_cells=args.min_cells, insert_database=args.insert), indent=2))


if __name__ == "__main__":
    main()
```

> **Why repoint module-level paths instead of passing args?** It keeps each
> stage's standalone CLI (`extract.py`, `in.py`, …) simple while letting the
> pipeline isolate every run. The temp `.running/<uuid>` directory guarantees a
> failed run leaves no half-written output in the published folders.

---

## 15. Email intake — `api/`

These two scripts pull depot attachments from the mail-reader service and drop
them into `files/api/` named by depot. They are **separate** from `pipeline.py`
(run them on their own schedule).

### 15.1 `api/sender_extractor.py`

Finds the original sender's domain from an email body preview. The first email
address in the body is the original sender; keep `@` + domain.

```python
import urllib.request
import urllib.parse
import re
import html
import json


def extract_original_sender_domain(json_response):
    try:
        data = json.loads(json_response)
        html_body = data.get("body_content", "")
    except Exception:
        html_body = json_response

    clean_text = html.unescape(html_body)
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'

    all_emails = re.findall(email_pattern, clean_text)
    sender_email = all_emails[0] if all_emails else "Not Found"

    if sender_email != "Not Found" and "@" in sender_email:
        return "@" + sender_email.split("@")[-1]
    return "Not Found"


def get_sender_domain_for_id(message_id):
    encoded_id = urllib.parse.quote(message_id)
    html_url = f"https://mail-reader.sarjak.com/api/attachment/internet-id/{encoded_id}/html"
    try:
        with urllib.request.urlopen(html_url, timeout=15) as response:
            if response.status == 200:
                json_body = response.read().decode('utf-8', errors='ignore')
                return extract_original_sender_domain(json_body)
    except Exception:
        pass
    return "Error/Not Found"


if __name__ == "__main__":
    import sys
    test_id = "<SL2P216MB137530AF8528AA6583E7BF2AA1112@SL2P216MB1375.KORP216.PROD.OUTLOOK.COM>"
    if len(sys.argv) > 1:
        test_id = sys.argv[1]
    print(f"Original Sender Domain: {get_sender_domain_for_id(test_id)}")
```

### 15.2 `api/processor.py`

Discovers pending `VISHNU_DEPOT` emails, resolves sender → depot, downloads only
`SARJAK` attachments (skips `ARCON`), and writes a `<file>.message-id` sidecar
for traceability.

```python
import os
import subprocess
import urllib.request
import urllib.parse
import json
import base64
import time
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent))
from sender_extractor import extract_original_sender_domain

CSV_ROOT = Path(__file__).resolve().parents[2]
ATTACHMENT_DIR = CSV_ROOT / "files" / "api"


def _load_env():
    env_path = CSV_ROOT / "info.txt"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_env()

MAIL_DB_SERVER = os.environ.get("MAIL_DB_SERVER", "10.1.0.6")
MAIL_DB_USER = os.environ.get("MAIL_DB_USER", "")
MAIL_DB_PASSWORD = os.environ.get("MAIL_DB_PASSWORD", "")
MAIL_DB_DATABASE = os.environ.get("PROCESS_EMAIL_DATABASE", "EMail_Reader_Process_Data")
SQLCMD = os.environ.get("SQLCMD_PATH", "sqlcmd")
SQLCMD_BASE = [SQLCMD, "-S", MAIL_DB_SERVER, "-C"]
if MAIL_DB_USER and MAIL_DB_PASSWORD:
    SQLCMD_BASE += ["-U", MAIL_DB_USER, "-P", MAIL_DB_PASSWORD]
else:
    SQLCMD_BASE += ["-E"]

SQL_QUERY = f"""
SELECT DISTINCT [internet_message_id]
FROM [{MAIL_DB_SERVER}].[{MAIL_DB_DATABASE}].[dbo].[tbl_Process_Emails]
WHERE [completed_at] IS NULL
  AND [Process] = 'VISHNU_DEPOT'
  AND NULLIF(LTRIM(RTRIM([internet_message_id])), '') IS NOT NULL
"""
POLL_SECONDS = 60 * 60


def get_message_ids():
    cmd = SQLCMD_BASE + ["-Q", SQL_QUERY, "-W", "-h", "-1"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except Exception as e:
        print(f"Error fetching IDs from database: {e}")
        return []


def get_depot_info(sender_domain):
    safe_domain = sender_domain.replace("'", "''")
    sql = (f"SELECT pd.PortId, pd.PortName FROM dbo.PortDetails pd "
           f"INNER JOIN dbo.LocationContacts lc ON pd.PortId = lc.PortId "
           f"WHERE lc.DepotContactEmail = '{safe_domain}' AND lc.IsDeleted = 0")
    cmd = SQLCMD_BASE + ["-Q", sql, "-W", "-h", "-1"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        output = result.stdout.strip().split()
        if len(output) >= 2:
            return output[0], " ".join(output[1:])
    except Exception as e:
        print(f"  - Depot Info Error: {e}")
    return None, "Not Found"


def should_process_attachment(filename):
    fn_upper = filename.upper()
    if "ARCON" in fn_upper:
        return False
    if "SARJAK" in fn_upper:
        return True
    return False


def save_base64_file(content_bytes_b64, target_path):
    try:
        file_data = base64.b64decode(content_bytes_b64)
        with open(target_path, 'wb') as f:
            f.write(file_data)
        return True
    except Exception as e:
        print(f"Error decoding/saving file: {e}")
        return False


def message_id_path(attachment_path):
    return attachment_path.with_name(f"{attachment_path.name}.message-id")


def get_body_preview(message_id):
    safe_id = message_id.replace("'", "''")
    sql = (f"SELECT [body_preview] "
           f"FROM [{MAIL_DB_SERVER}].[{MAIL_DB_DATABASE}].[dbo].[tbl_Process_Emails] "
           f"WHERE [internet_message_id] = '{safe_id}'")
    cmd = SQLCMD_BASE + ["-Q", sql, "-W", "-h", "-1"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except Exception as e:
        print(f"  - Body Preview Error: {e}")
        return ""


def process_id(message_id):
    encoded_id = urllib.parse.quote(message_id)
    attachments_url = f"https://mail-reader.sarjak.com/api/attachment/internet-id/{encoded_id}/external-attachments"
    print(f"Processing: {message_id}")

    sender_domain = "Not Found"
    port_id, port_name = None, "Not Found"
    try:
        body_preview = get_body_preview(message_id)
        if body_preview:
            sender_domain = extract_original_sender_domain(body_preview)
            print(f"  - Original Sender Domain: {sender_domain}")
            if sender_domain != "Not Found":
                port_id, port_name = get_depot_info(sender_domain)
                print(f"  - Identified Depot: {port_name} (ID: {port_id})")
    except Exception as e:
        print(f"  - Sender Resolution Error: {e}")

    try:
        with urllib.request.urlopen(attachments_url, timeout=15) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                attachments = data.get('attachments', []) if isinstance(data, dict) else []
                if attachments:
                    for att in attachments:
                        original_name = att.get('name') or att.get('fileName') or "Unknown"
                        if not should_process_attachment(original_name):
                            print(f"  - Skipping (Filter): {original_name}")
                            continue
                        content_b64 = att.get('contentBytes')
                        if content_b64:
                            suffix = Path(original_name).suffix
                            base_name = str(port_id) if port_id else Path(original_name).stem
                            ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)
                            counter = 1
                            while True:
                                new_name = f"{base_name}_{counter}{suffix}"
                                target = ATTACHMENT_DIR / new_name
                                if not target.exists():
                                    break
                                counter += 1
                            if save_base64_file(content_b64, target):
                                message_id_path(target).write_text(message_id, encoding="utf-8")
                                print(f"  - Saved attachment: {original_name} -> {new_name}")
                else:
                    print("  - No external attachments found.")
    except Exception as e:
        print(f"  - Attachments API Error: {e}")
    return sender_domain


def process_pending_ids():
    ids = get_message_ids()
    if not ids:
        print("No unprocessed IDs found in database.")
        return
    for mid in ids:
        try:
            process_id(mid)
        except Exception as e:
            print(f"Error processing {mid}: {e}")


if __name__ == "__main__":
    ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)
    if len(sys.argv) > 1:
        process_id(sys.argv[1])
    else:
        while True:
            try:
                process_pending_ids()
            except Exception as e:
                print(f"Poll cycle error: {e}")
            time.sleep(POLL_SECONDS)
```

> **Depot identity from filename:** because the attachment is saved as
> `<PortId>_<counter>.<ext>`, `plot_id_from_attachment_name` in `database.py`
> recovers the `PlotID` for inserts. If the depot is unresolved, the attachment
> keeps `<original-stem>_<counter>` and inserts requiring a PlotID are skipped.

---

## 16. End-to-end run & expected outputs

### 16.1 Run

```bash
cd csv
source .venv/bin/activate

# 1) (optional) pull attachments into files/api/
python code/api/processor.py "<internet-message-id>"

# 2) extract + report only (NO database writes)
python code/pipeline.py

# 3) extract + report + insert valid + errors + mark emails complete
python code/pipeline.py --insert

# process explicit files / a folder
python code/pipeline.py path/to/workbook.xlsx
python code/pipeline.py path/to/input-directory --insert

# tune header sensitivity
python code/pipeline.py --min-cells 4
```

### 16.2 Output tree

```
files/
├── processed/<YYYY-MM-DD_HH-MM-SS>/      # copies of the input workbooks
├── extraction/<YYYY-MM-DD_HH-MM-SS>/     # intermediate per-table .xlsx
└── results/<YYYY-MM-DD_HH-MM-SS>/
    ├── IN/                               # routed Gate-In tables
    ├── OUT/                              # routed Gate-Out tables
    ├── in.txt
    ├── out.txt
    ├── gate_in.json
    ├── gate_out.json
    └── gate_errors.json
```

### 16.3 JSON shapes

`gate_in.json` — list of `{"values": {...}}`:

```json
[
  {
    "values": {
      "PlotInID": 1234,
      "PlotID": 123,
      "ContainerId": 98765,
      "PlotInDate": "2026-06-10",
      "PlotInStatus": "P",
      "CreatedBy": 1,
      "Remarks": null,
      "BookingId": null,
      "OutBookingID": null,
      "ContainerStatusId": "2"
    }
  }
]
```

`gate_out.json` — list of `{"values": {...}}` with
`PlotOutId, BookingId, ContainerId, SealNo, Transporter, VehicleNo, PlotOutDate,
PlotOutTime, Remarks, CreatedBy, PlotOutStatus, PlotId, ContType,
ContainerStatusId` (+ optional `ErrorCode`).

`gate_errors.json` — same `values` plus `GateType` (`IN`/`OUT`); excludes
`DUPLICATE_RECORD`.

### 16.4 Run summary (stdout)

A JSON object with `workbooks`, `processed_dir`, `extraction_dir`, `results_dir`,
the five report/JSON paths, `database` (insert counts or `null`),
`internet_message_ids`, `completed_emails`, and `completed_at`.

---

## 17. Error-code reference

| Code | Gate | When | Inserted? |
|---|---|---|---|
| `INVALID_CONTAINER_NUMBER` | both (intermediate) | Row had no valid container in the extracted table. | n/a (intermediate only) |
| `NO_CONTAINER_ID` | IN, OUT | Container number not found in `ContainerEntry`. | No |
| `DUPLICATE_RECORD` | IN, OUT | IN: (ContainerId, date) exists; OUT: (ContainerId, date, BookingId) exists. | No; **excluded** from `gate_errors.json` |
| `INVALID_CONTAINER_STATUS_ID` | IN | Container status not in `{2, 7}`. | No |
| `NO_BOOKING_ID` | OUT | Booking value matched neither booking regex nor region fallback. **Preserved** through validation. | No |
| `INVALID_ECP_COUNT` | OUT | Extracted out-qty for a booking exceeds `booked − already plotted`. | No |

**Priority** — IN: `NO_CONTAINER_ID` → `DUPLICATE_RECORD` →
`INVALID_CONTAINER_STATUS_ID`. OUT: preserve `NO_BOOKING_ID` → `NO_CONTAINER_ID`
→ `DUPLICATE_RECORD` → `INVALID_ECP_COUNT`.

**Insert gating:** Gate-In inserts require no `ErrorCode` **and** non-null
`PlotID`. Gate-Out inserts require no `ErrorCode` **and** non-null `PlotId`.

---

## 18. Acceptance checklist

Work through this before calling the module done (maps to WORKFLOW §54–58):

**File level**
- [ ] Accepts `.xls`, `.xlt`, `.xlsx`, `.xlsm`, `.xltx`, `.xltm`.
- [ ] China chosen when CJK present; India default.
- [ ] `MONTH`/`MASTER` sheets excluded; `SHEET1` and `进场`/`出场` force-processed.
- [ ] Merged cells handled (top-left value spans the range).
- [ ] Headers detected dynamically (≥ 3 consecutive plain-text cells).
- [ ] Tables stop at the first fully blank row, clipped to header columns.

**Extraction level**
- [ ] Only rows with a valid container become records; containers uppercased.
- [ ] IN/OUT separated correctly; ambiguous tables not routed.
- [ ] Dates → `YYYY-MM-DD`, times → `HH:MM:SS.000`; raw kept on parse failure.
- [ ] IN uses first date/time; OUT uses last/rightmost date/time.
- [ ] Booking: regex → marker → region fallback; India never accepts weak fallback, China accepts `^\d{6}$`.
- [ ] Vehicle: marker → regex scan; blank allowed.

**Validation level**
- [ ] All six error codes fire under the right conditions, in priority order.
- [ ] `NO_BOOKING_ID` never overwritten by a lower-priority error.

**Output level**
- [ ] `in.txt`, `out.txt`, `gate_in.json`, `gate_out.json`, `gate_errors.json` produced.
- [ ] Duplicates excluded from `gate_errors.json`.
- [ ] Run artifacts under one timestamp; temp `.running/` removed.

**Insertion level (`--insert`)**
- [ ] Only error-free records with valid Plot IDs inserted.
- [ ] No duplicates, no missing mandatory IDs, no over-booking inserted.
- [ ] Failed records stored in `DepotMovementError`.
- [ ] Associated emails marked complete only on `--insert`.

---

## 19. Adding a new region

1. `cp code/countries/template.py code/countries/<region>.py`.
2. Set `COUNTRY_CODE`, `COUNTRY_NAME`, and a `LANGUAGE_PATTERN` that matches the
   region's script/language.
3. Fill in `CONTAINER_NUMBER` (usually the shared pattern), `DATE_PATTERN`,
   `TIME_PATTERN`, `BOOKING_ID`, `VEHICLE_NUMBER`, the `SHEET_SELECTION`
   markers, and the `FALLBACKS` (markers + `out_booking_fallback` +
   `default_error_code`).
4. Register it in `countries/__init__.py`:
   ```python
   from . import china, india, <region>
   COUNTRY_INTEGRATIONS = (china, <region>)   # order = detection priority
   ```
5. Keep India as `DEFAULT_INTEGRATION` (the fallback when no language matches).
6. Run `python -c "from countries import validate_integration, <region>; validate_integration(<region>)"`
   to confirm the contract is complete.

> The core engine (`extract.py`, `movement.py`, `in.py`, `out.py`,
> `database.py`) does **not** change when you add a region — that is the whole
> point of the contract.

---

**End of guide.** Build the files in the order of the table of contents, run
`python code/pipeline.py` against a sample workbook, and verify the output tree
in §16 before enabling `--insert`.
