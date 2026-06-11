"""
Guest segmentation engine.

Responsibilities
----------------
- Consolidate reservations into per-guest profiles (keyed by guest_email).
- Assign zero-to-many segments per profile from a configurable rule set.
- Compute the remarketing priority score (0-100).
- Persist results to the `guests` MongoDB collection.

All segment rule definitions live in `SEGMENT_RULES` so they can be tuned
without changing the engine code.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Channel taxonomies
# ---------------------------------------------------------------------------

DIRECT_SOURCES = {
    "Direct — Website",
    "Direct — Phone",
    "Direct — Email",
    "Direct — Repeat Guest",
}

OTA_SOURCES = {
    "Airbnb",
    "Booking.com",
    "Stayz",
    "VRBO",
    "Expedia",
    "Trip.com",
    "Other OTA",
}


def channel_of(source: str) -> str:
    if source in DIRECT_SOURCES:
        return "Direct"
    if source in OTA_SOURCES:
        return "OTA"
    return "Unknown"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_iso_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _days_between(a: Optional[str], b: Optional[str]) -> Optional[int]:
    da, db_ = _parse_iso_date(a), _parse_iso_date(b)
    if not da or not db_:
        return None
    return (db_ - da).days


def _median(values: List[float]) -> float:
    return float(statistics.median(values)) if values else 0.0


def _percentile(values: List[float], pct: float) -> float:
    """Return the pct'th percentile (0-100). Returns 0 if empty."""
    if not values:
        return 0.0
    xs = sorted(values)
    k = (len(xs) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    if f == c:
        return float(xs[f])
    return float(xs[f] + (xs[c] - xs[f]) * (k - f))


# ---------------------------------------------------------------------------
# Profile construction
# ---------------------------------------------------------------------------

def _initials(first: str, last: str, email: str) -> str:
    base = (first or "").strip() + " " + (last or "").strip()
    base = base.strip()
    if not base:
        base = (email or "?").split("@")[0]
    parts = [p for p in base.split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def build_profile(email: str, reservations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate one guest's reservation list into a profile dict (pre-segments)."""
    completed = [r for r in reservations if not r.get("is_cancelled")]
    cancelled = [r for r in reservations if r.get("is_cancelled")]

    # Pick guest name from most recent reservation
    reservations_sorted = sorted(
        reservations, key=lambda r: r.get("checkin_date") or "", reverse=True
    )
    latest = reservations_sorted[0] if reservations_sorted else {}
    first_name = latest.get("guest_first_name", "") or ""
    last_name = latest.get("guest_last_name", "") or ""

    # Stay aggregates (completed only — spec)
    total_stays = len(completed)
    lifetime_spend = round(sum(float(r.get("booking_value") or 0) for r in completed), 2)
    completed_dates = [r.get("checkin_date") for r in completed if r.get("checkin_date")]
    first_stay = min(completed_dates) if completed_dates else None
    last_stay = max(completed_dates) if completed_dates else None
    avg_booking_value = round(lifetime_spend / total_stays, 2) if total_stays else 0.0
    nights_list = [int(r.get("nights")) for r in completed if r.get("nights")]
    avg_los = round(sum(nights_list) / len(nights_list), 2) if nights_list else 0.0

    # Properties stayed at
    properties = sorted({r.get("property_name", "") for r in completed if r.get("property_name")})

    # Source aggregates
    source_counter: Dict[str, int] = {}
    for r in completed:
        s = r.get("classified_source") or "Unknown"
        source_counter[s] = source_counter.get(s, 0) + 1
    most_used_source = (
        max(source_counter.items(), key=lambda kv: kv[1])[0] if source_counter else None
    )
    # Primary channel category — based on completed stays first, otherwise cancellations
    if completed:
        channel_counts = {"Direct": 0, "OTA": 0, "Unknown": 0}
        for r in completed:
            channel_counts[channel_of(r.get("classified_source") or "")] += 1
        primary_channel = max(channel_counts.items(), key=lambda kv: kv[1])[0]
    elif cancelled:
        cancel_channels = [channel_of(r.get("classified_source") or "") for r in cancelled]
        primary_channel = max(set(cancel_channels), key=cancel_channels.count)
    else:
        primary_channel = "Unknown"

    # Cancellation aggregates
    cancellation_count = len(cancelled)
    total_bookings = len(reservations)
    cancellation_rate = round(
        (cancellation_count / total_bookings) * 100, 2
    ) if total_bookings else 0.0
    cancelled_values = [float(r.get("booking_value") or 0) for r in cancelled]
    avg_cancelled_value = round(sum(cancelled_values) / len(cancelled_values), 2) if cancelled_values else 0.0
    cancelled_channels = {channel_of(r.get("classified_source") or "") for r in cancelled}
    last_cancellation_date = max(
        [r.get("booking_date") or r.get("checkin_date") for r in cancelled if r.get("booking_date") or r.get("checkin_date")],
        default=None,
    )

    # Recovery indicator: cancelled but later completed a stay
    recovered = False
    if cancelled and completed:
        cancel_min = min(
            (r.get("booking_date") or r.get("checkin_date") for r in cancelled if r.get("booking_date") or r.get("checkin_date")),
            default=None,
        )
        completed_max = max((r.get("checkin_date") for r in completed if r.get("checkin_date")), default=None)
        if cancel_min and completed_max and completed_max > cancel_min:
            recovered = True

    return {
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
        "initials": _initials(first_name, last_name, email),
        "total_stays": total_stays,
        "lifetime_spend": lifetime_spend,
        "first_stay_date": first_stay,
        "last_stay_date": last_stay,
        "most_used_source": most_used_source,
        "primary_channel": primary_channel,
        "properties": properties,
        "cancellation_count": cancellation_count,
        "cancellation_rate": cancellation_rate,
        "avg_booking_value": avg_booking_value,
        "avg_length_of_stay": avg_los,
        "recovered": recovered,
        # internals used by segmentation/scoring
        "_avg_cancelled_value": avg_cancelled_value,
        "_cancelled_via_ota": "OTA" in cancelled_channels,
        "_cancelled_via_direct": "Direct" in cancelled_channels,
        "_last_cancellation_date": last_cancellation_date,
        "_completed_count": total_stays,
        "_total_bookings": total_bookings,
        "_source_counter": source_counter,
        "_reservations": reservations,
        "_completed": completed,
        "_cancelled": cancelled,
    }


# ---------------------------------------------------------------------------
# Segment rules — each predicate takes (profile, ctx) -> bool
# ctx provides cross-cohort stats (medians, percentiles).
# ---------------------------------------------------------------------------

def _all_completed_via(profile: Dict[str, Any], channel: str) -> bool:
    completed = profile["_completed"]
    if not completed:
        return False
    return all(channel_of(r.get("classified_source") or "") == channel for r in completed)


def _majority_via(profile: Dict[str, Any], channel: str) -> bool:
    completed = profile["_completed"]
    if not completed:
        return False
    n = sum(1 for r in completed if channel_of(r.get("classified_source") or "") == channel)
    return n > len(completed) / 2


def _months_since(iso_date: Optional[str]) -> Optional[float]:
    d = _parse_iso_date(iso_date)
    if not d:
        return None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return (now - d).days / 30.4375


SEGMENT_RULES: List[Dict[str, Any]] = [
    # --- Standard ---
    {
        "name": "Direct Loyal Guest",
        "kind": "standard",
        "description": "3+ completed stays, all via Direct channels",
        "predicate": lambda p, c: p["_completed_count"] >= 3 and _all_completed_via(p, "Direct"),
    },
    {
        "name": "OTA Loyal Guest",
        "kind": "standard",
        "description": "3+ completed stays, all via OTA channels",
        "predicate": lambda p, c: p["_completed_count"] >= 3 and _all_completed_via(p, "OTA"),
    },
    {
        "name": "OTA First-Time Guest",
        "kind": "standard",
        "description": "Exactly 1 stay via OTA, no cancellations",
        "predicate": lambda p, c: (
            p["_completed_count"] == 1
            and p["primary_channel"] == "OTA"
            and p["cancellation_count"] == 0
        ),
    },
    {
        "name": "OTA Repeat Guest",
        "kind": "standard",
        "description": "2+ stays, majority via OTA",
        "predicate": lambda p, c: p["_completed_count"] >= 2 and _majority_via(p, "OTA"),
    },
    {
        "name": "High Value Direct Guest",
        "kind": "standard",
        "description": "Direct guest, lifetime spend in top 25% of all guests",
        "predicate": lambda p, c: (
            p["primary_channel"] == "Direct"
            and p["_completed_count"] >= 1
            and p["lifetime_spend"] >= c["lifetime_spend_p75"]
            and c["lifetime_spend_p75"] > 0
        ),
    },
    {
        "name": "High Value OTA Guest",
        "kind": "standard",
        "description": "OTA guest, lifetime spend in top 25% of all guests",
        "predicate": lambda p, c: (
            p["primary_channel"] == "OTA"
            and p["_completed_count"] >= 1
            and p["lifetime_spend"] >= c["lifetime_spend_p75"]
            and c["lifetime_spend_p75"] > 0
        ),
    },
    {
        "name": "OTA Guest Most Likely to Convert",
        "kind": "standard",
        "description": "OTA guest, 2+ stays, zero cancellations, booking value above median",
        "predicate": lambda p, c: (
            p["primary_channel"] == "OTA"
            and p["_completed_count"] >= 2
            and p["cancellation_count"] == 0
            and p["avg_booking_value"] > c["avg_booking_value_median"]
        ),
    },
    {
        "name": "Direct Guest at Risk of Churning",
        "kind": "standard",
        "description": "Direct guest, last stay >12 months ago, previously had 2+ stays",
        "predicate": lambda p, c: (
            p["primary_channel"] == "Direct"
            and p["_completed_count"] >= 2
            and (_months_since(p["last_stay_date"]) or 0) > 12
        ),
    },
    # --- Cancellation segments ---
    {
        "name": "Cancelled — High Intent",
        "kind": "cancellation",
        "description": "1+ cancellation, avg cancelled value above overall median, zero completed stays",
        "predicate": lambda p, c: (
            p["cancellation_count"] >= 1
            and p["_completed_count"] == 0
            and p["_avg_cancelled_value"] > c["cancelled_value_median"]
            and c["cancelled_value_median"] > 0
        ),
    },
    {
        "name": "Cancelled — Repeat Canceller",
        "kind": "cancellation",
        "description": "2+ cancellations, zero completed stays",
        "predicate": lambda p, c: p["cancellation_count"] >= 2 and p["_completed_count"] == 0,
    },
    {
        "name": "Cancelled — Recovered Guest",
        "kind": "cancellation",
        "description": "Previously cancelled, subsequently completed 1+ stay",
        "predicate": lambda p, c: p["cancellation_count"] >= 1 and p["_completed_count"] >= 1 and p["recovered"],
    },
    {
        "name": "Cancelled — OTA Winback Target",
        "kind": "cancellation",
        "description": "Cancelled via OTA, zero completed stays, cancelled value above median",
        "predicate": lambda p, c: (
            p["cancellation_count"] >= 1
            and p["_completed_count"] == 0
            and p["_cancelled_via_ota"]
            and p["_avg_cancelled_value"] > c["cancelled_value_median"]
            and c["cancelled_value_median"] > 0
        ),
    },
]


def list_segment_definitions() -> List[Dict[str, str]]:
    """Expose segment metadata (name/kind/description) for the UI."""
    return [{"name": r["name"], "kind": r["kind"], "description": r["description"]} for r in SEGMENT_RULES]


def assign_segments(profile: Dict[str, Any], ctx: Dict[str, float]) -> List[str]:
    out = []
    for rule in SEGMENT_RULES:
        try:
            if rule["predicate"](profile, ctx):
                out.append(rule["name"])
        except Exception:
            # Defensive: bad rule shouldn't crash recompute
            continue
    return out


# ---------------------------------------------------------------------------
# Remarketing priority score
# ---------------------------------------------------------------------------

def compute_priority_score(profile: Dict[str, Any], ctx: Dict[str, float]) -> int:
    if profile["cancellation_count"] == 0:
        return 0

    score = 0.0

    # (a) Cancelled value vs overall median — up to 30 pts.
    # Linear: median value → 15 pts, 2x median or more → 30 pts, 0 → 0.
    med = ctx.get("cancelled_value_median", 0)
    avg_cancel = profile["_avg_cancelled_value"]
    if med > 0:
        ratio = avg_cancel / (2 * med)
        score += min(30.0, 30.0 * max(0.0, ratio))
    elif avg_cancel > 0:
        score += 15.0  # we have value but no comparator

    # (b) Recency of last cancellation — up to 25 pts.
    last = profile["_last_cancellation_date"]
    months = _months_since(last)
    if months is not None:
        if months <= 3:  # ≤90 days
            score += 25.0
        elif months >= 24:
            score += 0.0
        else:
            # sliding linear from 25 @ 3mo to 0 @ 24mo
            score += 25.0 * max(0.0, (24 - months) / (24 - 3))

    # (c) Recovery bonus
    if profile["recovered"]:
        score += 20.0

    # (d) OTA cancellation bonus
    if profile["_cancelled_via_ota"]:
        score += 15.0

    # (e) Repeat canceller penalty
    if profile["cancellation_count"] >= 2 and profile["_completed_count"] == 0:
        score -= 20.0

    return int(max(0, min(100, round(score))))


# ---------------------------------------------------------------------------
# Top-level recompute
# ---------------------------------------------------------------------------

def _compute_context(profiles: List[Dict[str, Any]]) -> Dict[str, float]:
    lifetime_spends = [p["lifetime_spend"] for p in profiles if p["_completed_count"] > 0]
    avg_values = [p["avg_booking_value"] for p in profiles if p["_completed_count"] > 0]
    cancelled_values = [p["_avg_cancelled_value"] for p in profiles if p["cancellation_count"] > 0]
    return {
        "lifetime_spend_p75": _percentile(lifetime_spends, 75),
        "avg_booking_value_median": _median(avg_values),
        "cancelled_value_median": _median(cancelled_values),
    }


async def recompute_all_guests(db) -> Dict[str, Any]:
    """
    Rebuild the `guests` collection from `reservations`.
    Idempotent: each call wipes and rewrites the collection.
    """
    cursor = db.reservations.find({}, {"_id": 0})
    all_res = await cursor.to_list(length=100000)

    # Group by guest_email (lowercase, trimmed). Skip rows with no email.
    by_email: Dict[str, List[Dict[str, Any]]] = {}
    for r in all_res:
        email = (r.get("guest_email") or "").strip().lower()
        if not email:
            continue
        by_email.setdefault(email, []).append(r)

    profiles_internal = [build_profile(email, rs) for email, rs in by_email.items()]
    ctx = _compute_context(profiles_internal)

    now = datetime.now(timezone.utc).isoformat()
    persisted: List[Dict[str, Any]] = []
    for p in profiles_internal:
        segments = assign_segments(p, ctx)
        score = compute_priority_score(p, ctx)
        doc = {
            "id": p["email"],  # email is the natural id
            "email": p["email"],
            "first_name": p["first_name"],
            "last_name": p["last_name"],
            "initials": p["initials"],
            "total_stays": p["total_stays"],
            "lifetime_spend": p["lifetime_spend"],
            "first_stay_date": p["first_stay_date"],
            "last_stay_date": p["last_stay_date"],
            "most_used_source": p["most_used_source"],
            "primary_channel": p["primary_channel"],
            "properties": p["properties"],
            "cancellation_count": p["cancellation_count"],
            "cancellation_rate": p["cancellation_rate"],
            "avg_booking_value": p["avg_booking_value"],
            "avg_length_of_stay": p["avg_length_of_stay"],
            "recovered": p["recovered"],
            "remarketing_priority_score": score,
            "segments": segments,
            "updated_at": now,
        }
        persisted.append(doc)

    # Replace the collection contents atomically (for our scale this is fine).
    await db.guests.delete_many({})
    if persisted:
        await db.guests.insert_many([d.copy() for d in persisted])

    return {
        "guest_count": len(persisted),
        "context": ctx,
        "updated_at": now,
    }
