"""Shared pydantic models — the contracts between pipeline stages."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Direction(str, Enum):
    IN = "IN"
    OUT = "OUT"
    UNRESOLVED = "UNRESOLVED"


class LogicalCell(BaseModel):
    row: int
    end_row: int
    start_col: int
    end_col: int
    value: Any = None
    is_horizontal_merge: bool = False
    is_vertical_merge: bool = False


class HeaderRun(BaseModel):
    sheet: str
    row: int
    start_col: int
    end_col: int
    cell_count: int
    values: list[str] = Field(default_factory=list)
    cells: list[LogicalCell] = Field(default_factory=list)
    title: str = ""


class TableRegion(BaseModel):
    sheet: str
    header: HeaderRun
    data_start_row: int
    data_end_row: int
    start_col: int
    end_col: int


class RawRow(BaseModel):
    source_row: int
    cells: list[str] = Field(default_factory=list)


class ExtractedTable(BaseModel):
    sheet: str
    title: str
    header: list[str] = Field(default_factory=list)
    rows: list[RawRow] = Field(default_factory=list)
    row_errors: list[str] = Field(default_factory=list)
    direction: Direction = Direction.UNRESOLVED
    saved_path: Optional[str] = None


# --- Extraction shapes (loose, human-friendly) ---

class GateInRecord(BaseModel):
    container_no: str = ""
    date: str = ""
    time: str = ""
    remark: str = ""
    container_status: str = ""
    error_code: str = ""


class GateOutRecord(BaseModel):
    container_id: str = ""
    booking_id: str = ""
    seal_no: str = ""
    plot_out_date: str = ""
    plot_out_time: str = ""
    transporter: str = ""
    vehicle_no: str = ""
    remarks: str = ""
    error_code: str = ""


# --- Final DB-schema shapes (Section 18) ---

class GateInValues(BaseModel):
    PlotInID: Optional[int] = None
    PlotID: Optional[int] = None
    ContainerId: Optional[int] = None
    PlotInDate: str = ""
    PlotInStatus: str = "P"
    CreatedBy: int = 1
    Remarks: str = ""
    BookingId: Optional[int] = None
    OutBookingID: Optional[int] = None
    ContainerStatusId: Optional[int] = None
    ErrorCode: Optional[str] = None


class GateOutValues(BaseModel):
    PlotOutId: Optional[int] = None
    BookingId: Optional[int] = None
    ContainerId: Optional[int] = None
    SealNo: str = ""
    Transporter: str = ""
    VehicleNo: str = ""
    PlotOutDate: str = ""
    PlotOutTime: str = ""
    Remarks: str = ""
    CreatedBy: int = 1
    PlotOutStatus: str = "P"
    PlotId: Optional[int] = None
    ContType: Optional[str] = None
    ContainerStatusId: Optional[int] = None
    ErrorCode: Optional[str] = None


class JobResult(BaseModel):
    file: str
    message_id: str = ""
    region: str = ""
    in_records: list[GateInValues] = Field(default_factory=list)
    out_records: list[GateOutValues] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)
    db_counts: dict = Field(default_factory=dict)
    status: str = "ok"


class RunSummary(BaseModel):
    workbooks: list[str] = Field(default_factory=list)
    dirs: dict = Field(default_factory=dict)
    db_counts: dict = Field(default_factory=dict)
    message_ids: list[str] = Field(default_factory=list)
    completed_at: str = ""


class Job(BaseModel):
    file_path: str
    message_id: str = ""
    port_id: Optional[int] = None
