"""Template for a new country integration.

Copy this file, replace the metadata and regex values, then register the module
in countries/__init__.py. Keep the exported names unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Pattern


# Integration metadata and worksheet-language detection.
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


# Worksheet-selection regex, language markers, exclusions, and fallbacks.
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


# Shared regex used by both IN and OUT processing.
CONTAINER_NUMBER = re.compile(r"\b[A-Z]{3}[UJZ]\d{7}\b", re.IGNORECASE)
DATE_PATTERN = re.compile(r"(?!x)x")
TIME_PATTERN = re.compile(r"(?!x)x")

# Regex used only by OUT processing.
BOOKING_ID = re.compile(r"(?!x)x")
VEHICLE_NUMBER = re.compile(r"(?!x)x")

# Explicit direction contracts consumed by in.py and out.py.
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

# Non-regex defaults and parsing fallbacks owned by this integration.
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
