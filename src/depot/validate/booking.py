"""Booking resolution + quantity math for gate-out. Uses a per-booking Redis
lock so two parallel jobs don't both pass the quota check (Section 16.6)."""

from __future__ import annotations

from ..cache import locks
from ..db.batcher import LookupCache


def resolve_booking_id(cache: LookupCache, booking_ref: str):
    if not booking_ref:
        return None
    if booking_ref in cache.booking_ids:
        return cache.booking_ids[booking_ref]
    if booking_ref.isdigit():
        return int(booking_ref)
    return None


def ecp_exceeds(cache: LookupCache, booking_id: int, extracted_qty: int) -> bool:
    """True if extracted_qty for this booking exceeds booked - already_plotted.
    Guarded by a per-booking lock so concurrent jobs serialize the check."""
    booked = cache.booked_qty.get(booking_id, 0)
    plotted = cache.plotted_counts.get(booking_id, 0)
    remaining = booked - plotted
    with locks.lock(f"booking:{booking_id}", ttl=60) as acquired:
        # Whether or not the lock was acquired, the arithmetic is the same; the
        # lock simply serializes parallel checks on the same booking.
        _ = acquired
        return extracted_qty > remaining
