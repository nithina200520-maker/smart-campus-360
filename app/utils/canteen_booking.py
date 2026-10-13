"""
Phase 6: Smart Canteen booking engine.

Centralizes the order lifecycle, pickup-slot capacity accounting, and the
configurable teacher-first allocation policy so the routes stay thin and the
rules are unit-testable in isolation.

Allocation guarantees:
- Stock, per-slot order capacity, and confirmed orders are always respected.
- A share of every slot may be reserved for VERIFIED teachers, but the
  reservation is released once the slot opens, so student orders are never
  silently discarded or indefinitely delayed: they either get a seat, or the
  checkout is rejected with an explicit reason plus the next open slot.
"""
from datetime import datetime, timedelta

from app.database import db
from app.models import CanteenOrder, CanteenPickupSlot

# ---------------------------------------------------------------- lifecycle

# 'placed' is the legacy pre-Phase-6 value and is treated as Pending everywhere.
PENDING = ('placed', 'pending')
ACTIVE = PENDING + ('confirmed', 'preparing', 'ready')
TERMINAL = ('collected', 'cancelled', 'refunded')
REFUND = ('refund_requested', 'refund_processing')

# Statuses that occupy stock / slot capacity. A refund requested AFTER cooking
# started still consumes the slot (the food was made), a cancellation does not.
CONSUMING = PENDING + ('confirmed', 'preparing', 'ready', 'collected') + REFUND

# Allowed canteen-admin transitions (customer-side transitions live in routes).
ALLOWED_TRANSITIONS = {
    'placed': {'confirmed', 'preparing', 'ready', 'collected', 'cancelled'},
    'pending': {'confirmed', 'cancelled', 'refunded'},
    'confirmed': {'preparing', 'cancelled', 'refund_requested'},
    'preparing': {'ready', 'refund_requested', 'cancelled'},
    'ready': {'collected', 'refund_requested'},
    'refund_requested': {'refund_processing', 'refunded', 'preparing', 'ready'},
    'refund_processing': {'refunded'},
    'collected': set(),
    'cancelled': set(),
    'refunded': set(),
}


def normalize_status(status: str) -> str:
    """Map the legacy 'placed' value onto the Phase 6 vocabulary."""
    return 'pending' if status == 'placed' else status


def can_transition(current: str, new: str) -> bool:
    return new in ALLOWED_TRANSITIONS.get(current, set())


def consumes_capacity(status: str) -> bool:
    return status in CONSUMING


# ---------------------------------------------------------------- capacity

def slot_booked_counts(slot_id: int):
    """(total, teacher) counts of capacity-consuming orders already booked."""
    rows = (
        db.session.query(CanteenOrder.order_status, CanteenOrder.is_priority)
        .filter(CanteenOrder.slot_id == slot_id)
        .all()
    )
    total = teacher = 0
    for status, is_priority in rows:
        if consumes_capacity(status):
            total += 1
            if is_priority:
                teacher += 1
    return total, teacher


def slot_availability(slot: CanteenPickupSlot, config, is_priority: bool, now: datetime = None):
    """
    Compute whether one order may take a seat in this slot under the current
    teacher-first policy. Returns a dict with the decision and its inputs so
    callers can explain the outcome to the user (nothing is silent).

    Reservation rule: `reserve = ceil(capacity * ratio)` seats are held for
    verified teachers while the slot is still in the future. Unused reserved
    seats are released at slot start, so students are never pushed out
    indefinitely. Priority customers may always use the full capacity.
    """
    now = now or datetime.now()
    capacity = int(slot.order_capacity or 0)
    total_booked, teacher_booked = slot_booked_counts(slot.id)

    enabled = bool(config.get('CANTEEN_TEACHER_PRIORITY_ENABLED', True))
    ratio = float(config.get('CANTEEN_TEACHER_RESERVE_RATIO', 0.25))
    slot_open = now >= slot.starts_at
    reserve = 0 if (slot_open or not enabled or not ratio > 0) else int(-(-capacity * ratio // 1))  # ceil
    reserve_effective = max(0, reserve - teacher_booked)  # only unused teacher seats

    remaining = max(0, capacity - total_booked)
    student_remaining = max(0, remaining - reserve_effective)

    allowed = student_remaining > 0 if not is_priority else remaining > 0
    reason = None
    if not allowed:
        reason = 'slot_full' if remaining == 0 else 'teacher_reserve'

    return {
        'slot': slot,
        'capacity': capacity,
        'booked': total_booked,
        'teacher_booked': teacher_booked,
        'teacher_reserved': reserve,
        'remaining': remaining,
        'remaining_for_me': student_remaining if not is_priority else remaining,
        'allowed': allowed,
        'reason': reason,
        'opens_at': slot.starts_at,
        'is_open': slot_open,
    }


def upcoming_slots(days: int = 7, now: datetime = None):
    """Active slots from now until `days` ahead, ordered chronologically."""
    now = now or datetime.now()
    horizon = now + timedelta(days=days)
    return (
        CanteenPickupSlot.query
        .filter(CanteenPickupSlot.is_active.is_(True),
                CanteenPickupSlot.slot_date >= now.date(),
                CanteenPickupSlot.slot_date <= horizon.date())
        .order_by(CanteenPickupSlot.slot_date.asc(), CanteenPickupSlot.start_time.asc())
        .all()
    )


def bookable_slots(config, is_priority: bool, max_lead_days: int = 7, now: datetime = None):
    """Upcoming slots with availability info, each annotated 'available' bool."""
    now = now or datetime.now()
    lead = timedelta(minutes=int(config.get('CANTEEN_MIN_LEAD_MINS', 15)))
    results = []
    for slot in upcoming_slots(days=max_lead_days, now=now):
        if slot.starts_at - now < lead:
            continue  # too close to start for the kitchen to prepare
        info = slot_availability(slot, config, is_priority, now=now)
        results.append(info)
    return results


def next_available_slot(config, is_priority: bool, exclude_id=None, now: datetime = None):
    """First bookable slot for this customer (used to redirect full-slot orders)."""
    for info in bookable_slots(config, is_priority, now=now):
        if exclude_id and info['slot'].id == exclude_id:
            continue
        if info['allowed']:
            return info['slot']
    return None


# ---------------------------------------------------------------- estimates

def estimate_ready_at(slot: CanteenPickupSlot, max_prep_mins: int, ahead_count: int,
                      config, now: datetime = None) -> datetime:
    """
    Realistic pickup estimate: the slot opening time, plus the item with the
    longest preparation time, plus the kitchen load already queued ahead in the
    same slot (orders that will be served before this one).
    """
    now = now or datetime.now()
    base = slot.starts_at if slot and slot.starts_at > now else now
    per_order = int(config.get('CANTEEN_PREP_MIN_PER_ORDER', 4))
    return base + timedelta(minutes=int(max_prep_mins) + ahead_count * per_order)


def queue_position(order: CanteenOrder, now: datetime = None):
    """
    (ahead_count, total_ahead_including_self) for an order in its slot, using
    the same service order the kitchen queue applies: teacher-first, then
    earliest booking. Returns (0, 0) for legacy slot-less orders.
    """
    if not order.slot_id:
        return 0, 0
    now = now or datetime.now()
    peers = (
        CanteenOrder.query
        .filter(CanteenOrder.slot_id == order.slot_id,
                CanteenOrder.order_status.in_(PENDING + ('confirmed', 'preparing')))
        .order_by(CanteenOrder.is_priority.desc(), CanteenOrder.created_at.asc(), CanteenOrder.id.asc())
        .all()
    )
    total = len(peers)
    ahead = 0
    for peer in peers:
        if peer.id == order.id:
            break
        ahead += 1
    return ahead, total


def max_prep_minutes(order: CanteenOrder) -> int:
    """Longest preparation time among the order's line items (safe on legacy rows)."""
    from app.models import CanteenItem
    prep = 10
    items = []
    for line in order.items:
        item = CanteenItem.query.get(line.item_id)
        if item and item.preparation_time_mins:
            items.append(int(item.preparation_time_mins))
    if items:
        prep = max(items)
    return prep
