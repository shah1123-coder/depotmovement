"""Gate-In validation -> GateInValues. Error priority, stop at first hit
(Section 16.4):
  1. NO_CONTAINER_ID
  2. DUPLICATE_RECORD
  3. INVALID_CONTAINER_STATUS_ID
"""

from __future__ import annotations

from ..db import lookups
from ..db.batcher import LookupCache
from ..errors import ErrorCode
from ..models import GateInRecord, GateInValues
from ..normalize import fields
from ..settings import get_settings


def validate_gate_in(records: list[GateInRecord], cache: LookupCache,
                     plot_id: int | None) -> list[GateInValues]:
    valid_status = set(get_settings().gate_in_status_valid)
    out: list[GateInValues] = []

    for rec in records:
        key = fields.normalize_container(rec.container_no)
        date_str = fields.normalize_date(rec.date)
        container_id = cache.container_ids.get(key)
        info = cache.container_info.get(key, {})
        status_id = info.get("status_id")

        error_code = None
        if container_id is None:
            error_code = ErrorCode.NO_CONTAINER_ID.value
        elif date_str and lookups.check_in_duplicate(container_id, date_str):
            error_code = ErrorCode.DUPLICATE_RECORD.value
        elif status_id not in valid_status:
            error_code = ErrorCode.INVALID_CONTAINER_STATUS_ID.value

        out.append(GateInValues(
            PlotID=plot_id,
            ContainerId=container_id,
            PlotInDate=date_str,
            Remarks=fields.normalize_empty(rec.remark),
            ContainerStatusId=status_id,
            ErrorCode=error_code,
        ))
    return out
