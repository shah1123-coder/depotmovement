"""Gate-Out validation -> GateOutValues. Error priority (Section 16.5):
  1. PRESERVE existing NO_BOOKING_ID (never overwrite)
  2. NO_CONTAINER_ID
  3. DUPLICATE_RECORD
  4. INVALID_ECP_COUNT
"""

from __future__ import annotations

from collections import defaultdict

from ..db import lookups
from ..db.batcher import LookupCache
from ..errors import ErrorCode
from ..models import GateOutRecord, GateOutValues
from ..normalize import fields
from . import booking


def validate_gate_out(records: list[GateOutRecord], cache: LookupCache,
                      plot_id: int | None) -> list[GateOutValues]:
    out: list[GateOutValues] = []

    # Tally extracted quantity per booking across this set of records.
    extracted_per_booking: dict[int, int] = defaultdict(int)
    resolved_ids: list[int | None] = []
    for rec in records:
        bid = booking.resolve_booking_id(cache, rec.booking_id)
        resolved_ids.append(bid)
        if bid is not None and rec.error_code != ErrorCode.NO_BOOKING_ID.value:
            extracted_per_booking[bid] += 1

    for rec, booking_id in zip(records, resolved_ids):
        key = fields.normalize_container(rec.container_id)
        date_str = fields.normalize_date(rec.plot_out_date)
        time_str = fields.normalize_time(rec.plot_out_time)
        container_id = cache.container_ids.get(key)
        info = cache.container_info.get(key, {})
        cont_type = cache.container_types.get(key)

        # 1. preserve NO_BOOKING_ID set at extraction
        if rec.error_code == ErrorCode.NO_BOOKING_ID.value:
            error_code = ErrorCode.NO_BOOKING_ID.value
        elif container_id is None:
            error_code = ErrorCode.NO_CONTAINER_ID.value
        elif date_str and booking_id is not None and \
                lookups.check_out_duplicate(container_id, date_str, booking_id):
            error_code = ErrorCode.DUPLICATE_RECORD.value
        elif booking_id is not None and booking.ecp_exceeds(
                cache, booking_id, extracted_per_booking.get(booking_id, 0)):
            error_code = ErrorCode.INVALID_ECP_COUNT.value
        else:
            error_code = None

        out.append(GateOutValues(
            BookingId=booking_id,
            ContainerId=container_id,
            SealNo=fields.normalize_empty(rec.seal_no),
            Transporter=fields.normalize_empty(rec.transporter),
            VehicleNo=fields.normalize_empty(rec.vehicle_no),
            PlotOutDate=date_str,
            PlotOutTime=time_str,
            Remarks=fields.normalize_empty(rec.remarks),
            PlotId=plot_id,
            ContType=cont_type,
            ContainerStatusId=info.get("status_id"),
            ErrorCode=error_code,
        ))
    return out
