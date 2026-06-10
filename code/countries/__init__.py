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
