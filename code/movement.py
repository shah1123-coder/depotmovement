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

# Regex for English words with boundaries
STANDALONE_IN = re.compile(r"(?<![A-Z0-9])IN(?![A-Z0-9])", re.IGNORECASE)
STANDALONE_OUT = re.compile(r"(?<![A-Z0-9])OUT(?![A-Z0-9])", re.IGNORECASE)

# Chinese characters (partial match anywhere)
CHINESE_IN = "\u8fdb"  # 进
CHINESE_OUT = "\u51fa" # 出

# Fallback regex for workbook names
GATE_IN_RE = re.compile(r"GATE\s*IN", re.IGNORECASE)
GATE_OUT_RE = re.compile(r"GATE\s*OUT", re.IGNORECASE)

def sanitize_path_part(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
    return cleaned or "untitled"

def movement_direction(value: str) -> str | None:
    # Partial match for Chinese characters or English keywords
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
        
        # Suffix logic: only if exactly one direction is present across the whole workbook folder
        suffix = ""
        if len(found_dirs) == 1:
            suffix = f"-{list(found_dirs)[0]}"

        for root, dirs, files in os.walk(workbook_dir):
            excel_files = sorted(file for file in files if file.lower().endswith(".xlsx"))
            for file in files:
                if not file.lower().endswith(".xlsx"):
                    continue
                
                table_path = Path(root) / file
                direction = movement_direction(file)
                if direction is None:
                    direction = movement_direction(Path(root).name)
                    if direction is None:
                        # Final fallback to original workbook name
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
                    # Apply the determined suffix
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
