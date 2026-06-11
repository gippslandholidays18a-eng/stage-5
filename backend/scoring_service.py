"""
Stage 3 — Scoring engine + OTA commission tracking.

Adds four 0-100 scores to every guest profile:
- direct_conversion_score
- lifetime_value_score
- rebooking_score
- revenue_opportunity_score (composite)

Also computes `estimated_commission_cost` on every OTA reservation using
configurable rates stored in the `platform_settings` collection.

Public entrypoint: `recalculate_all_scores(db)` — call after recompute_all_guests.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from segmentation_service import OTA_SOURCES


# ---------------------------------------------------------------------------
# Commission settings — stored in platform_settings collection
# ---------------------------------------------------------------------------

DEFAULT_COMMISSION_RATES: Dict[str, float] = {
    "Airbnb": 15.5,
    "Booking.com": 13.9,
    "Expedia": 15.0,
    "Trip.com": 15.0,
    "VRBO": 8.0,
    "Stayz": 10.0,        # not in spec; sensible default
    "Other OTA": 12.0,
}

SETTINGS_DOC_ID = "commission_rates"


async def ensure_commission_settings(db) -> Dict[str, float]:
    doc = await db.platform_settings.find_one({"id": SETTINGS_DOC_ID})
    if doc and doc.get("rates"):
        # Merge in any new defaults that weren't set when the doc was created
        merged = {**DEFAULT_COMMISSION_RATES, **doc["rates"]}
        if merged != doc["rates"]:
            await db.platform_settings.update_one(
                {"id": SETTINGS_DOC_ID},
                {"$set": {"rates": merged, "updated_at": datetime.now(timezone.utc).isoformat()}},
            )
        return merged
    initial = {
        "id": SETTINGS_DOC_ID,
        "rates": dict(DEFAULT_COMMISSION_RATES),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.platform_settings.update_one(
        {"id": SETTINGS_DOC_ID},
        {"$setOnInsert": initial},
        upsert=True,
    )
    return dict(DEFAULT_COMMISSION_RATES)


async def get_commission_rates(db) -> Dict[str, float]:
    return await ensure_commission_settings(db)


async def set_commission_rates(db, rates: Dict[str, float]) -> Dict[str, float]:
    # Coerce values to floats and clamp to reasonable range
    cleaned = {}
    for k, v in rates.items():
        try:
            fv = float(v)
            if 0 <= fv <= 100:
                cleaned[k] = round(fv, 2)
        except Exception:
            continue
    now = datetime.now(timezone.utc).isoformat()
    await db.platform_settings.update_one(
        {"id": SETTINGS_DOC_ID},
        {"$set": {"rates": cleaned, "updated_at": now}, "$setOnInsert": {"id": SETTINGS_DOC_ID}},
        upsert=True,
    )
    return cleaned


def _commission_for(rate: float, value: float) -> float:
    return round(float(value or 0) * (float(rate) / 100.0), 2)


async def apply_commission_costs(db) -> int:
    """Recompute estimated_commission_cost on every reservation (idempotent)."""
    rates = await get_commission_rates(db)
    fallback = rates.get("Other OTA", DEFAULT_COMMISSION_RATES["Other OTA"])
    touched = 0
    async for r in db.reservations.find(
        {}, {"id": 1, "classified_source": 1, "booking_value": 1}
    ):
        src = r.get("classified_source") or ""
        if src in OTA_SOURCES:
            rate = rates.get(src, fallback)
            cost = _commission_for(rate, r.get("booking_value") or 0)
            await db.reservations.update_one(
                {"id": r["id"]},
                {"$set": {"estimated_commission_cost": cost, "commission_rate_used": rate}},
            )
        else:
            await db.reservations.update_one(
                {"id": r["id"]},
                {"$set": {"estimated_commission_cost": 0.0, "commission_rate_used": 0.0}},
            )
        touched += 1
    return touched


# ---------------------------------------------------------------------------
# Scoring primitives
# ---------------------------------------------------------------------------

def _parse_date(s: Optional[str]):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _months_since(iso: Optional[str]) -> Optional[float]:
    d = _parse_date(iso)
    if not d:
        return None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return (now - d).days / 30.4375


def predict_future_stays(profile: Dict[str, Any]) -> int:
    """Historical stay frequency extrapolated 24 months forward."""
    n = profile.get("total_stays", 0)
    if n == 0:
        return 0
    first = _parse_date(profile.get("first_stay_date"))
    last = _parse_date(profile.get("last_stay_date"))
    if n == 1 or not first or not last or first == last:
        return 2  # default forward-looking assumption for single-stayers
    span_days = max(1, (last - first).days)
    stays_per_day = (n - 1) / span_days
    return max(0, int(round(stays_per_day * 730.5)))  # 730.5d ≈ 24mo


def compute_raw_ltv(profile: Dict[str, Any]) -> float:
    lifetime = float(profile.get("lifetime_spend") or 0)
    avg = float(profile.get("avg_booking_value") or 0)
    future = predict_future_stays(profile)
    return round(lifetime + avg * future, 2)


def _avg_lead_time(reservations: List[Dict[str, Any]]) -> float:
    days: List[int] = []
    for r in reservations:
        if r.get("is_cancelled"):
            continue
        b = _parse_date(r.get("booking_date"))
        c = _parse_date(r.get("checkin_date"))
        if b and c:
            d = (c - b).days
            if d >= 0:
                days.append(d)
    return float(statistics.mean(days)) if days else 0.0


def compute_direct_conversion_score(
    profile: Dict[str, Any],
    ctx: Dict[str, float],
    reservations: List[Dict[str, Any]],
) -> int:
    channel = profile.get("primary_channel")
    if channel == "Direct":
        return 100
    if channel != "OTA":
        return 0

    score = 0
    n = profile.get("total_stays", 0)
    if n >= 3:
        score += 30
    elif n == 2:
        score += 20
    elif n == 1:
        score += 10

    if profile.get("cancellation_count", 0) == 0:
        score += 20

    median_avg = ctx.get("avg_booking_value_median", 0)
    if (profile.get("avg_booking_value") or 0) > median_avg and median_avg > 0:
        score += 15

    avg_lead = _avg_lead_time(reservations)
    median_lead = ctx.get("lead_time_median", 0)
    if avg_lead > median_lead and median_lead > 0:
        score += 10

    if len(profile.get("properties") or []) > 1:
        score += 10

    months = _months_since(profile.get("last_stay_date"))
    if months is not None and months <= 12:
        score += 10

    if "OTA Guest Most Likely to Convert" in (profile.get("segments") or []):
        score += 5

    # Repeat canceller penalty
    if profile.get("cancellation_count", 0) >= 2 and n == 0:
        score -= 30

    return max(0, min(100, score))


def compute_rebooking_score(profile: Dict[str, Any], ctx: Dict[str, float]) -> int:
    score = 0
    n = profile.get("total_stays", 0)
    if n >= 4:
        score += 45
    elif n == 3:
        score += 35
    elif n == 2:
        score += 25
    elif n == 1:
        score += 15

    months = _months_since(profile.get("last_stay_date"))
    if months is not None:
        if months <= 6:
            score += 20
        elif months <= 12:
            score += 10
        elif months > 24:
            score -= 20

    if profile.get("cancellation_count", 0) == 0:
        score += 15

    if profile.get("recovered"):
        score += 10

    if len(profile.get("properties") or []) > 1:
        score += 10

    los_median = ctx.get("los_median", 0)
    if (profile.get("avg_length_of_stay") or 0) > los_median and los_median > 0:
        score += 5

    if profile.get("cancellation_count", 0) >= 2 and n == 0:
        score -= 40

    return max(0, min(100, score))


def compute_lifetime_value_normalised(raw: float, all_raws: List[float]) -> int:
    if not all_raws:
        return 0
    max_raw = max(all_raws)
    min_raw = min(all_raws)
    if max_raw == min_raw:
        return 100 if max_raw > 0 else 0
    return int(round((raw - min_raw) / (max_raw - min_raw) * 100))


def revenue_opportunity_score(d: int, ltv: int, rebook: int) -> int:
    return int(round(d * 0.35 + ltv * 0.40 + rebook * 0.25))


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def recalculate_all_scores(db) -> Dict[str, Any]:
    # 1. Commission per reservation
    await apply_commission_costs(db)

    # 2. Load reservations grouped by guest_email
    res_cursor = db.reservations.find({}, {"_id": 0})
    all_res = await res_cursor.to_list(length=200000)
    by_email: Dict[str, List[Dict[str, Any]]] = {}
    for r in all_res:
        em = (r.get("guest_email") or "").lower().strip()
        if em:
            by_email.setdefault(em, []).append(r)

    # 3. Load guests
    g_cursor = db.guests.find({}, {"_id": 0})
    guests = await g_cursor.to_list(length=100000)

    # 4. Portfolio medians
    avg_values = [g["avg_booking_value"] for g in guests
                  if g.get("total_stays", 0) > 0 and g.get("avg_booking_value")]
    los_values = [g["avg_length_of_stay"] for g in guests
                  if g.get("total_stays", 0) > 0 and g.get("avg_length_of_stay")]
    lead_times: List[int] = []
    for r in all_res:
        if r.get("is_cancelled"):
            continue
        b = _parse_date(r.get("booking_date"))
        c = _parse_date(r.get("checkin_date"))
        if b and c and (c - b).days >= 0:
            lead_times.append((c - b).days)

    ctx = {
        "avg_booking_value_median": float(statistics.median(avg_values)) if avg_values else 0.0,
        "los_median": float(statistics.median(los_values)) if los_values else 0.0,
        "lead_time_median": float(statistics.median(lead_times)) if lead_times else 0.0,
    }

    # 5. Raw LTV pass — needed for normalisation
    raws_by_email: Dict[str, float] = {g["id"]: compute_raw_ltv(g) for g in guests}
    all_raws = list(raws_by_email.values())

    # 6. Apply all four scores per guest
    for g in guests:
        em = g["id"]
        res_for = by_email.get(em, [])
        raw = raws_by_email[em]
        ltv_norm = compute_lifetime_value_normalised(raw, all_raws)
        dconv = compute_direct_conversion_score(g, ctx, res_for)
        rebook = compute_rebooking_score(g, ctx)
        rev_op = revenue_opportunity_score(dconv, ltv_norm, rebook)
        await db.guests.update_one(
            {"id": em},
            {"$set": {
                "raw_ltv_value": raw,
                "predicted_future_stays": predict_future_stays(g),
                "lifetime_value_score": ltv_norm,
                "direct_conversion_score": dconv,
                "rebooking_score": rebook,
                "revenue_opportunity_score": rev_op,
                "scores_updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )

    return {
        "guests_scored": len(guests),
        "context": ctx,
        "raw_ltv_range": [min(all_raws) if all_raws else 0, max(all_raws) if all_raws else 0],
    }


# ---------------------------------------------------------------------------
# Dashboard helpers (pure)
# ---------------------------------------------------------------------------

def commission_summary_by_source(reservations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate commission costs per OTA platform across non-cancelled reservations."""
    buckets: Dict[str, Dict[str, float]] = {}
    for r in reservations:
        src = r.get("classified_source") or ""
        if src not in OTA_SOURCES:
            continue
        if r.get("is_cancelled"):
            continue
        b = buckets.setdefault(src, {"bookings": 0, "revenue": 0.0, "commission": 0.0})
        b["bookings"] += 1
        b["revenue"] += float(r.get("booking_value") or 0)
        b["commission"] += float(r.get("estimated_commission_cost") or 0)
    out = []
    for src, b in buckets.items():
        out.append({
            "source": src,
            "bookings": int(b["bookings"]),
            "revenue": round(b["revenue"], 2),
            "commission": round(b["commission"], 2),
            "avg_commission_per_booking": round(b["commission"] / b["bookings"], 2) if b["bookings"] else 0.0,
        })
    out.sort(key=lambda x: x["commission"], reverse=True)
    return out


def estimated_savings_if_top_converted(
    guests: List[Dict[str, Any]],
    reservations: List[Dict[str, Any]],
    pct: float = 20.0,
) -> float:
    """If the top N% of OTA guests (by direct_conversion_score) had booked direct,
    sum of commission they generated."""
    ota_guests = [g for g in guests if g.get("primary_channel") == "OTA"]
    if not ota_guests:
        return 0.0
    ota_guests.sort(key=lambda g: g.get("direct_conversion_score", 0), reverse=True)
    top_n = max(1, int(round(len(ota_guests) * (pct / 100.0))))
    top_emails = {g["email"] for g in ota_guests[:top_n]}
    total = 0.0
    for r in reservations:
        if r.get("is_cancelled"):
            continue
        em = (r.get("guest_email") or "").lower().strip()
        if em in top_emails:
            total += float(r.get("estimated_commission_cost") or 0)
    return round(total, 2)
