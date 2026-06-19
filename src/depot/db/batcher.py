"""Collect all container numbers / booking refs across every record in the run,
run the lookups ONCE, and hand back in-memory dicts for validation."""

from __future__ import annotations

from typing import Iterable

from ..models import GateInRecord, GateOutRecord
from . import lookups


class LookupCache:
    def __init__(self):
        self.container_ids: dict[str, int] = {}
        self.container_info: dict[str, dict] = {}
        self.container_types: dict[str, str] = {}
        self.booking_ids: dict[str, int] = {}
        self.booked_qty: dict[int, int] = {}
        self.plotted_counts: dict[int, int] = {}

    def container_key(self, container_no: str) -> str:
        return (container_no or "").upper().replace(" ", "")


def build_cache(in_records: Iterable[GateInRecord],
                out_records: Iterable[GateOutRecord]) -> LookupCache:
    cache = LookupCache()
    containers: set[str] = set()
    booking_refs: set[str] = set()

    for rec in in_records:
        if rec.container_no:
            containers.add(cache.container_key(rec.container_no))
    for rec in out_records:
        if rec.container_id:
            containers.add(cache.container_key(rec.container_id))
        if rec.booking_id:
            booking_refs.add(rec.booking_id)

    container_list = list(containers)
    cache.container_ids = lookups.get_container_ids(container_list)
    cache.container_info = lookups.get_container_info(container_list)
    cache.container_types = lookups.get_container_types(container_list)

    cache.booking_ids = lookups.get_booking_ids(list(booking_refs))
    resolved_booking_ids = list({v for v in cache.booking_ids.values()})
    cache.booked_qty = lookups.get_booked_quantities(resolved_booking_ids)
    cache.plotted_counts = lookups.get_plotted_counts(resolved_booking_ids)
    return cache
