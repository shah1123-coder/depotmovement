"""China/Chinese worksheet integration."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Pattern


# Integration metadata and worksheet-language detection.
COUNTRY_CODE = "CN"
COUNTRY_NAME = "China"
LANGUAGE_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


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
    in_language_marker="\u8fdb\u573a",
    out_language_marker="\u51fa\u573a",
    excluded_name_parts=("MONTH", "MASTER"),
    always_process_names=("SHEET1",),
    direct_in_names=("\u8fdb\u573a",),
    direct_out_names=("\u51fa\u573a",),
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
    r"[\u4eac\u6d25\u6caa\u6e1d\u5180\u8c6b\u4e91\u8fbd\u9ed1\u6e58"
    r"\u7696\u9c81\u65b0\u82cf\u6d59\u8d63\u9102\u6842\u7518\u664b"
    r"\u8499\u9655\u5409\u95fd\u8d35\u7ca4\u9752\u85cf\u5ddd\u5b81"
    r"\u743c][A-Z][\u00b7\-]?[A-Z0-9]{5,6}\b",
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
    in_remark_markers=("remark", "\u5907\u6ce8"),
    out_booking_markers=("\u5355\u53f7",),
    out_booking_fallback=re.compile(r"^\d{6}$"),
    out_seal_markers=("seal",),
    out_transporter_markers=("transporter",),
    out_remark_markers=("remark", "\u5907\u6ce8"),
    out_vehicle_markers=("\u573a\u8f66\u724c",),
)
