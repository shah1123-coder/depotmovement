"""China/Chinese worksheet integration."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Pattern


# Integration metadata and worksheet-language detection.
COUNTRY_CODE = "CN"
COUNTRY_NAME = "China"
LANGUAGE_PATTERN = re.compile(r"[㐀-䶿一-鿿豈-﫿]")


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
