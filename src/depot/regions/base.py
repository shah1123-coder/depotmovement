"""RegionProfile: a parsed region YAML with compiled regex + helper methods.

All region-specific behaviour lives here, driven entirely by config. A new
region requires only a new YAML file (Section 7) — never a core change.
"""

from __future__ import annotations

import re
from typing import Optional, Pattern

from pydantic import BaseModel, ConfigDict

from ..models import Direction


class SheetRules(BaseModel):
    exclude_if_name_contains: list[str] = []
    always_process_names: list[str] = []
    direct_in_names: list[str] = []
    direct_out_names: list[str] = []
    recognized_names: list[str] = []


class RegionProfile(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    language: str
    sheet_rules: SheetRules
    raw_regex: dict[str, str]
    markers: dict[str, list[str]]
    direction_in_tokens: list[str] = []
    direction_out_tokens: list[str] = []

    # compiled patterns (populated in build)
    rx_container: Pattern
    rx_booking_main: Pattern
    rx_booking_fallback: Pattern
    rx_time: Pattern
    rx_vehicle: Pattern
    rx_standalone_in: Pattern
    rx_standalone_out: Pattern
    rx_gate_in: Pattern
    rx_gate_out: Pattern
    rx_email: Pattern
    rx_booked_qty: Pattern
    rx_date: Pattern

    @classmethod
    def build(cls, data: dict) -> "RegionProfile":
        rx = data["regex"]
        ci = re.IGNORECASE
        return cls(
            name=data["name"],
            language=data["language"],
            sheet_rules=SheetRules(**data.get("sheet_rules", {})),
            raw_regex=rx,
            markers=data.get("markers", {}),
            direction_in_tokens=data.get("direction_in_tokens", []),
            direction_out_tokens=data.get("direction_out_tokens", []),
            rx_container=re.compile(rx["container"], ci),
            rx_booking_main=re.compile(rx["booking_main"], ci),
            rx_booking_fallback=re.compile(rx["booking_fallback"], ci),
            rx_time=re.compile(rx["time"], ci),
            rx_vehicle=re.compile(rx["vehicle"], ci),
            rx_standalone_in=re.compile(rx["standalone_in"], ci),
            rx_standalone_out=re.compile(rx["standalone_out"], ci),
            rx_gate_in=re.compile(rx["gate_in"], ci),
            rx_gate_out=re.compile(rx["gate_out"], ci),
            rx_email=re.compile(rx["email"], ci),
            rx_booked_qty=re.compile(rx["booked_qty"], ci),
            rx_date=re.compile(rx["date"]),
        )

    # --- field finders ---
    def find_container(self, text: str) -> Optional[str]:
        if not text:
            return None
        m = self.rx_container.search(text)
        return m.group(0).upper() if m else None

    def find_booking(self, text: str) -> Optional[str]:
        if not text:
            return None
        m = self.rx_booking_main.search(text) or self.rx_booking_fallback.search(text)
        return m.group(0) if m else None

    def find_time(self, text: str) -> Optional[str]:
        if not text:
            return None
        m = self.rx_time.search(text)
        return m.group(0) if m else None

    def find_vehicle(self, text: str) -> Optional[str]:
        if not text:
            return None
        m = self.rx_vehicle.search(text)
        return m.group(0) if m else None

    def find_date(self, text: str) -> Optional[str]:
        if not text:
            return None
        m = self.rx_date.search(text)
        return m.group(0) if m else None

    # --- direction ---
    def detect_direction(self, text: str) -> Direction:
        if not text:
            return Direction.UNRESOLVED
        has_in = bool(self.rx_standalone_in.search(text) or self.rx_gate_in.search(text)) \
            or any(tok in text for tok in self.direction_in_tokens)
        has_out = bool(self.rx_standalone_out.search(text) or self.rx_gate_out.search(text)) \
            or any(tok in text for tok in self.direction_out_tokens)
        if has_in and has_out:
            return Direction.UNRESOLVED
        if has_in:
            return Direction.IN
        if has_out:
            return Direction.OUT
        return Direction.UNRESOLVED

    # --- sheet helpers (operate on uppercased name) ---
    def is_excluded_sheet(self, name: str) -> bool:
        up = name.upper()
        return any(tok.upper() in up for tok in self.sheet_rules.exclude_if_name_contains)

    def is_forced_sheet(self, name: str) -> bool:
        up = name.upper()
        forced = (self.sheet_rules.always_process_names
                  + self.sheet_rules.direct_in_names
                  + self.sheet_rules.direct_out_names)
        return any(tok.upper() == up or tok.upper() in up for tok in forced)

    def is_recognized_sheet(self, name: str) -> bool:
        up = name.upper()
        return any(tok.upper() in up for tok in self.sheet_rules.recognized_names)

    def is_direct_in_sheet(self, name: str) -> bool:
        up = name.upper()
        return any(tok.upper() in up for tok in self.sheet_rules.direct_in_names)

    def is_direct_out_sheet(self, name: str) -> bool:
        up = name.upper()
        return any(tok.upper() in up for tok in self.sheet_rules.direct_out_names)
