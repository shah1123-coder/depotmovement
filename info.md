# The Absolute Atomic Reference: Excel Extraction & Reporting Pipeline

This document provides a line-of-logic specification for every component in the `code/` directory relative to the `csv/` project root. It is the definitive blueprint for the modular country-specific integration system.

---

## 1. Modularization Blueprint
- **Architecture:** All country-specific Regex patterns, header markers, and extraction fallbacks are encapsulated within the `countries/` module.
- **Orchestration:** Operational scripts (`in.py`, `out.py`, `extract.py`) dynamically load the correct integration based on worksheet language detection.

---

## 2. Module: `pipeline.py` (The Orchestrator)

### Function Signatures & Atomic Logic
- `discover_workbooks(inputs: list[Path]) -> list[Path]`:
    - **Logic:** Initializes a `workbooks` dict for uniqueness. Filters by `SUPPORTED_EXCEL_SUFFIXES` and excludes temporary `~$` files.
- `run_pipeline(inputs: list[Path], min_cells: int = 3) -> dict`:
    - **Logic:** Coordinates the full lifecycle: `Extraction` -> `Categorization` -> `Reporting`.

---

## 3. Module: `extract.py` (The Detection Engine)

### Function Signatures & Atomic Logic
- `detect_headers_in_sheet(sheet, min_cells) -> list[HeaderRun]`:
    - **Logic:** Identifies continuous runs of logical cells. Treats merged ranges as single logical cells.
- `should_process_sheet(sheet_name: str) -> bool`:
    - **Logic:** Uses `countries.sheet_selection_for_name` to apply country-specific sheet name regex (e.g., Chinese markers `进场` / `出场` or English `GATE IN` / `GATE OUT`).

---

## 4. Module: `countries/` (Country Integrations)

### Core Components
- `__init__.py`: Detects the country by scanning sheet text for language-specific patterns (e.g., Chinese characters). Defaults to the Indian integration.
- `china.py` / `india.py`: Contain the `FALLBACKS` dataclass which defines:
    - **Markers:** Lists of strings to find columns (e.g., `备注`, `单号`, `场车牌`).
    - **Regex:** Fallback patterns (e.g., 6-digit Booking ID fallback).
    - **Formats:** Date and time format variations for parsing.

---

## 5. Module: `in.py` (IN Movement Reporter)

### Function Signatures & Atomic Logic
- `find_remark_column(...)`:
    - **Logic:** Scans all cells for markers defined in the country's `FALLBACKS.in_remark_markers`.
- `extract_records(...)`:
    - **Logic:** Extracts `Container #`, `Date`, `Time`, and `Remark` using country-specific patterns and normalization logic.

---

## 6. Module: `out.py` (OUT Movement Reporter)

### Function Signatures & Atomic Logic
- `find_header_column_for_markers(...)`:
    - **Logic:** Returns the **rightmost** column matching any of the provided markers.
- `extract_records(...)`:
    - **Logic:** Implements multi-step fallback discovery:
        1. **Booking ID:** Regex Match -> Header Marker -> 6-digit Fallback Regex.
        2. **Vehicle #:** Header Marker -> Representative Row Regex Search.
        3. **Remarks/Seal/Transporter:** Header Marker Discovery.

---

## 7. Module: `movement.py` (The Categorizer)

### Function Signatures & Atomic Logic
- `movement_direction(value: str) -> str | None`:
    - **Logic:** Detects direction using English keywords (`IN`/`OUT`) and Chinese characters (`进`/`出`).
- `categorize_and_copy(...)`:
    - **Logic:** Synchronizes the `extraction/` folder into `results/IN` or `results/OUT`, handling filename collisions with numeric suffixes.

---

## 8. Comprehensive Pattern Catalog (Base Patterns)

| Pattern | Default Regex / Marker | Purpose |
| :--- | :--- | :--- |
| Container | `\b[A-Z]{3}[UJZ]\d{7}\b` | Identity |
| Booking | `\b[A-Za-z]{3}/[A-Za-z]{3}/\d{6}\b` | Linkage |
| Date | `\b(?:\d{1,2}[./ -]\d{1,2}...)\b` | Context |
| Time | `\b([01]?\d|2[0-3]):([0-5]\d)...` | Context |
| Booking Fallback | `^\d{6}$` (China specific) | Linkage Fallback |
| China Remark | `备注` | Chinese Remarks |
| China Booking | `单号` | Chinese Booking ID |
| China Vehicle | `场车牌` | Chinese Vehicle # |
