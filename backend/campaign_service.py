"""
Stage 5 — Campaign recommendation engine.

Reads from the existing `guests` and `reservations` collections (rebuilt by
Stages 2 + 3 on every import). No emails are sent — this module produces
ready-to-export audience lists, recommended offers, and content briefs.

Storage in platform_settings:
- id='offers'           — { offers: [...] }
- id='campaign_targets' — { target_direct_pct: 40 }
- id='campaign_content' — { [audience_key]: { subject_lines, sms, key_points, tone, send_timing } }
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from segmentation_service import DIRECT_SOURCES, OTA_SOURCES, channel_of


# ---------------------------------------------------------------------------
# Audience definitions — single source of truth
# ---------------------------------------------------------------------------

def _months_since(iso: Optional[str]) -> Optional[float]:
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(iso)
    except Exception:
        return None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return (now - d).days / 30.4375


AUDIENCES: Dict[str, Dict[str, Any]] = {
    # --- OTA Conversion tab -------------------------------------------------
    "ota_conversion_high": {
        "name": "High priority OTA conversion targets",
        "description": "OTA guests scored 70+ with 2+ stays and zero cancellations. Hottest direct-booking conversion audience.",
        "tab": "OTA Conversion",
        "goal": "Convert to direct",
        "campaign_type": "Email sequence",
        "recommended_offer": "DIRECT15",
        "send_timing": "Immediately post-stay, 30-day follow-up",
        "conversion_rate": 0.15,
        "predicate": lambda g: (
            g.get("primary_channel") == "OTA"
            and (g.get("direct_conversion_score") or 0) > 70
            and (g.get("total_stays") or 0) >= 2
            and (g.get("cancellation_count") or 0) == 0
        ),
        "sort_key": lambda g: -(g.get("revenue_opportunity_score") or 0),
    },
    "ota_conversion_medium": {
        "name": "Medium priority OTA conversion targets",
        "description": "OTA guests with direct_conversion_score 50-70 — nurture audience.",
        "tab": "OTA Conversion",
        "goal": "Nurture toward direct",
        "campaign_type": "Email sequence",
        "recommended_offer": "DIRECT10",
        "send_timing": "30 days post-stay, repeat quarterly",
        "conversion_rate": 0.08,
        "predicate": lambda g: (
            g.get("primary_channel") == "OTA"
            and 50 <= (g.get("direct_conversion_score") or 0) <= 70
        ),
        "sort_key": lambda g: -(g.get("direct_conversion_score") or 0),
    },
    "airbnb_winback": {
        "name": "Airbnb-specific winback",
        "description": "Airbnb guests with 2+ stays and direct_conversion_score above 50.",
        "tab": "OTA Conversion",
        "goal": "Convert Airbnb repeat to direct",
        "campaign_type": "Single email",
        "recommended_offer": "DIRECT10",
        "send_timing": "Within 7 days of last Airbnb checkout",
        "conversion_rate": 0.10,
        "predicate": lambda g: (
            g.get("most_used_source") == "Airbnb"
            and (g.get("total_stays") or 0) >= 2
            and (g.get("direct_conversion_score") or 0) > 50
        ),
        "sort_key": lambda g: -(g.get("direct_conversion_score") or 0),
    },
    "booking_winback": {
        "name": "Booking.com-specific winback",
        "description": "Booking.com guests with 2+ stays and direct_conversion_score above 50.",
        "tab": "OTA Conversion",
        "goal": "Convert Booking.com repeat to direct",
        "campaign_type": "Single email",
        "recommended_offer": "DIRECT10",
        "send_timing": "Within 7 days of last Booking.com checkout",
        "conversion_rate": 0.10,
        "predicate": lambda g: (
            g.get("most_used_source") == "Booking.com"
            and (g.get("total_stays") or 0) >= 2
            and (g.get("direct_conversion_score") or 0) > 50
        ),
        "sort_key": lambda g: -(g.get("direct_conversion_score") or 0),
    },
    "stayz_winback": {
        "name": "Stayz-specific winback",
        "description": "Stayz guests with 2+ stays and direct_conversion_score above 50.",
        "tab": "OTA Conversion",
        "goal": "Convert Stayz repeat to direct",
        "campaign_type": "Single email",
        "recommended_offer": "DIRECT10",
        "send_timing": "Within 7 days of last Stayz checkout",
        "conversion_rate": 0.10,
        "predicate": lambda g: (
            g.get("most_used_source") == "Stayz"
            and (g.get("total_stays") or 0) >= 2
            and (g.get("direct_conversion_score") or 0) > 50
        ),
        "sort_key": lambda g: -(g.get("direct_conversion_score") or 0),
    },
    # --- Guest Retention tab ------------------------------------------------
    "direct_loyal": {
        "name": "Direct loyal guests · VIP",
        "description": "Direct Loyal Guest segment — your most retained customers. Treat as VIPs.",
        "tab": "Guest Retention",
        "goal": "Retain & deepen relationship",
        "campaign_type": "Single email + occasional SMS",
        "recommended_offer": "LOYALGUEST",
        "send_timing": "Quarterly + 7 days before peak season",
        "conversion_rate": 0.35,
        "predicate": lambda g: "Direct Loyal Guest" in (g.get("segments") or []),
        "sort_key": lambda g: -(g.get("revenue_opportunity_score") or 0),
    },
    "high_value_direct": {
        "name": "High-value direct guests",
        "description": "Top 25% of direct guests by lifetime spend.",
        "tab": "Guest Retention",
        "goal": "Retain & deepen",
        "campaign_type": "Single email",
        "recommended_offer": "VIP5",
        "send_timing": "Within 14 days post-stay",
        "conversion_rate": 0.30,
        "predicate": lambda g: "High Value Direct Guest" in (g.get("segments") or []),
        "sort_key": lambda g: -(g.get("lifetime_spend") or 0),
    },
    "direct_at_risk": {
        "name": "Direct guests at risk of churning",
        "description": "Direct guests with 2+ prior stays whose last stay was over 12 months ago.",
        "tab": "Guest Retention",
        "goal": "Retain · prevent churn",
        "campaign_type": "Email sequence",
        "recommended_offer": "MISSYOU10",
        "send_timing": "Immediately + 30 days follow-up",
        "conversion_rate": 0.12,
        "predicate": lambda g: "Direct Guest at Risk of Churning" in (g.get("segments") or []),
        "sort_key": lambda g: -(g.get("lifetime_value_score") or 0),
    },
    # --- Win-back & Re-engagement tab --------------------------------------
    "cancelled_high_intent": {
        "name": "Cancelled high intent · top remarketing priority",
        "description": "Guests who cancelled with high booking value but no completed stays. Highest priority remarketing.",
        "tab": "Win-Back & Re-engagement",
        "goal": "Win back lost booking",
        "campaign_type": "Single email + SMS",
        "recommended_offer": "COMEBACK15",
        "send_timing": "Within 14 days of cancellation",
        "conversion_rate": 0.18,
        "predicate": lambda g: "Cancelled — High Intent" in (g.get("segments") or []),
        "sort_key": lambda g: -(g.get("remarketing_priority_score") or 0),
    },
    "cancelled_ota_winback": {
        "name": "Cancelled OTA winback targets",
        "description": "OTA cancellations with above-median booking value. Direct alternative.",
        "tab": "Win-Back & Re-engagement",
        "goal": "Win back as direct booking",
        "campaign_type": "Single email",
        "recommended_offer": "COMEBACK15",
        "send_timing": "Within 14 days of cancellation",
        "conversion_rate": 0.15,
        "predicate": lambda g: "Cancelled — OTA Winback Target" in (g.get("segments") or []),
        "sort_key": lambda g: -(g.get("remarketing_priority_score") or 0),
    },
    "recovered_guests": {
        "name": "Recovered guests · VIP",
        "description": "Previously cancelled then completed a stay. Proven converters — high lifetime value potential.",
        "tab": "Win-Back & Re-engagement",
        "goal": "Reward & retain",
        "campaign_type": "Single email",
        "recommended_offer": "VIP5",
        "send_timing": "30 days post-completed-stay",
        "conversion_rate": 0.25,
        "predicate": lambda g: "Cancelled — Recovered Guest" in (g.get("segments") or []),
        "sort_key": lambda g: -(g.get("revenue_opportunity_score") or 0),
    },
    "lapsed_all": {
        "name": "Lapsed guests (18+ months)",
        "description": "Any guest whose last stay was over 18 months ago. Worth one re-engagement touch.",
        "tab": "Win-Back & Re-engagement",
        "goal": "Re-engage",
        "campaign_type": "Single email",
        "recommended_offer": "MISSYOU10",
        "send_timing": "Once, then quarterly thereafter",
        "conversion_rate": 0.04,
        "predicate": lambda g: (
            (_months_since(g.get("last_stay_date")) or 0) > 18
            and (g.get("total_stays") or 0) >= 1
        ),
        "sort_key": lambda g: -(g.get("lifetime_spend") or 0),
    },
    "single_stay_ota": {
        "name": "Single-stay OTA guests",
        "description": "OTA First-Time Guests who haven't returned. Nurture sequence audience.",
        "tab": "Win-Back & Re-engagement",
        "goal": "Convert to repeat (ideally direct)",
        "campaign_type": "Email sequence",
        "recommended_offer": "DIRECT10",
        "send_timing": "14 days post-stay, then 60 days",
        "conversion_rate": 0.06,
        "predicate": lambda g: "OTA First-Time Guest" in (g.get("segments") or []),
        "sort_key": lambda g: -(g.get("direct_conversion_score") or 0),
    },
}

TABS = ["OTA Conversion", "Guest Retention", "Win-Back & Re-engagement"]


# ---------------------------------------------------------------------------
# Default offer library + content templates
# ---------------------------------------------------------------------------

DEFAULT_OFFERS = [
    {"code": "DIRECT10", "name": "10% off direct", "description": "10% discount on the next direct booking", "discount_type": "percentage", "discount_value": 10, "applies_to": "all", "active": True, "expires_at": None, "category": "Direct booking incentive"},
    {"code": "DIRECT15", "name": "15% off direct (3+ stays)", "description": "15% discount for guests with 3+ OTA stays", "discount_type": "percentage", "discount_value": 15, "applies_to": "all", "active": True, "expires_at": None, "category": "Direct booking incentive"},
    {"code": "EARLYACCESS", "name": "Peak-season early access", "description": "Early access to peak season inventory before OTA release", "discount_type": "none", "discount_value": 0, "applies_to": "all", "active": True, "expires_at": None, "category": "Direct booking incentive"},
    {"code": "FLEXCANCEL", "name": "Flexible cancellation", "description": "Flexible cancellation terms not offered through OTAs", "discount_type": "none", "discount_value": 0, "applies_to": "all", "active": True, "expires_at": None, "category": "Direct booking incentive"},
    {"code": "LOYALGUEST", "name": "Loyal guest late checkout", "description": "Complimentary late checkout for direct guests with 3+ stays", "discount_type": "none", "discount_value": 0, "applies_to": "all", "active": True, "expires_at": None, "category": "Loyalty"},
    {"code": "VIP5", "name": "Fifth stay VIP upgrade", "description": "Room upgrade or complimentary night on the 5th stay", "discount_type": "none", "discount_value": 0, "applies_to": "all", "active": True, "expires_at": None, "category": "Loyalty"},
    {"code": "REFERRAL20", "name": "$20 referral credit", "description": "$20 credit for any guest who refers a new booker", "discount_type": "fixed", "discount_value": 20, "applies_to": "all", "active": True, "expires_at": None, "category": "Loyalty"},
    {"code": "COMEBACK15", "name": "15% comeback offer", "description": "15% off for cancelled guests rebooking", "discount_type": "percentage", "discount_value": 15, "applies_to": "all", "active": True, "expires_at": None, "category": "Win-back"},
    {"code": "WEVECHANGED", "name": "We've changed (no discount)", "description": "Personalised message noting property improvements — no discount", "discount_type": "none", "discount_value": 0, "applies_to": "all", "active": True, "expires_at": None, "category": "Win-back"},
    {"code": "MISSYOU10", "name": "Miss-you 10% off", "description": "10% off for guests who haven't stayed in 18+ months", "discount_type": "percentage", "discount_value": 10, "applies_to": "all", "active": True, "expires_at": None, "category": "Win-back"},
    {"code": "OFFSEASON20", "name": "Off-season 20%", "description": "20% off stays during designated low season months", "discount_type": "percentage", "discount_value": 20, "applies_to": "all", "active": True, "expires_at": None, "category": "Seasonal"},
    {"code": "LASTMINUTE", "name": "Last-minute gap filler", "description": "Last-minute deal for gaps within 14 days", "discount_type": "percentage", "discount_value": 15, "applies_to": "all", "active": True, "expires_at": None, "category": "Seasonal"},
]

DEFAULT_CONTENT: Dict[str, Dict[str, Any]] = {
    "ota_conversion_high": {
        "subject_lines": [
            "An exclusive direct rate, just for you",
            "Your loyalty deserves more — save 15% next time",
            "Skip the booking fees on your next stay",
        ],
        "sms": "Hi {first_name}, book direct next time and save 15% with DIRECT15. Same property, lower price. Reply STOP to opt out.",
        "key_points": [
            "Acknowledge their previous stays",
            "Frame the discount as commission savings shared back",
            "Highlight flexible cancellation + direct concierge",
        ],
        "tone": "exclusive",
        "send_timing": "7 days post-stay, repeat at 30 days",
    },
    "ota_conversion_medium": {
        "subject_lines": [
            "A small thank-you for your stay",
            "We'd love to host you again — direct this time",
            "10% off when you book with us directly",
        ],
        "sms": "Hi {first_name}, thanks for staying with us. Book direct next time for 10% off — use DIRECT10.",
        "key_points": ["Soft nurture, no pressure", "Mention property news or seasonal updates"],
        "tone": "warm",
        "send_timing": "30 days post-stay",
    },
    "cancelled_high_intent": {
        "subject_lines": [
            "We held your spot — 15% off if you rebook",
            "Sorry plans changed — here's a flexible alternative",
            "Your booking value matters to us",
        ],
        "sms": "Hi {first_name}, sorry your plans changed. We've reserved 15% off (code COMEBACK15) if you'd like to rebook within 14 days.",
        "key_points": ["Acknowledge the cancellation without judgement", "Emphasise flexible cancellation policy", "Offer a fast-track booking link"],
        "tone": "warm",
        "send_timing": "Within 14 days of cancellation",
    },
    "direct_at_risk": {
        "subject_lines": [
            "It's been a while — we'd love to have you back",
            "Your favourite property misses you",
            "10% off your next stay, on us",
        ],
        "sms": "Hi {first_name}, we miss having you with us. Here's 10% off your next stay — code MISSYOU10.",
        "key_points": ["Reference their previous favourite property", "Mention what has changed", "Soft 10% offer"],
        "tone": "re-engagement",
        "send_timing": "Immediately + 30-day follow-up",
    },
    "direct_loyal": {
        "subject_lines": [
            "You're one of our most valued guests",
            "VIP perks for your next stay",
            "Late checkout, room upgrades, and more — just for you",
        ],
        "sms": "Hi {first_name}, you're a VIP guest with us. Late checkout & room upgrade are yours next stay — just reply YES.",
        "key_points": ["Address by first name", "Emphasise exclusivity", "Acknowledge total stay count"],
        "tone": "exclusive",
        "send_timing": "Quarterly + 7 days before peak season",
    },
}


def _default_content_for(audience_key: str, aud: Dict[str, Any]) -> Dict[str, Any]:
    if audience_key in DEFAULT_CONTENT:
        return DEFAULT_CONTENT[audience_key]
    return {
        "subject_lines": [
            f"{aud['name']} — a quick note",
            "We'd love to have you back",
            "Something special, just for you",
        ],
        "sms": "Hi {first_name}, we'd love to see you stay with us again.",
        "key_points": ["Personalise with first name and most recent property", "Keep tone aligned with goal"],
        "tone": "warm" if "Retention" in aud["tab"] else "re-engagement",
        "send_timing": aud.get("send_timing", "Within 14 days"),
    }


# ---------------------------------------------------------------------------
# Settings collection helpers
# ---------------------------------------------------------------------------

OFFERS_DOC = "offers"
TARGETS_DOC = "campaign_targets"
CONTENT_DOC = "campaign_content"


async def ensure_campaign_settings(db) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()

    offers_doc = await db.platform_settings.find_one({"id": OFFERS_DOC})
    if not offers_doc:
        await db.platform_settings.insert_one({
            "id": OFFERS_DOC, "offers": [dict(o) for o in DEFAULT_OFFERS], "updated_at": now,
        })

    targets_doc = await db.platform_settings.find_one({"id": TARGETS_DOC})
    if not targets_doc:
        await db.platform_settings.insert_one({
            "id": TARGETS_DOC, "target_direct_pct": 40, "updated_at": now,
        })

    content_doc = await db.platform_settings.find_one({"id": CONTENT_DOC})
    if not content_doc:
        seeded = {k: _default_content_for(k, v) for k, v in AUDIENCES.items()}
        await db.platform_settings.insert_one({
            "id": CONTENT_DOC, "content": seeded, "updated_at": now,
        })

    return {"seeded": True}


async def get_offers(db) -> List[Dict[str, Any]]:
    doc = await db.platform_settings.find_one({"id": OFFERS_DOC}, {"_id": 0})
    return (doc or {}).get("offers", [])


async def upsert_offer(db, offer: Dict[str, Any]) -> List[Dict[str, Any]]:
    offers = await get_offers(db)
    code = (offer.get("code") or "").strip().upper()
    if not code:
        raise ValueError("code is required")
    offer["code"] = code
    found = False
    for i, o in enumerate(offers):
        if o.get("code") == code:
            offers[i] = {**o, **offer}
            found = True
            break
    if not found:
        offers.append({
            "code": code,
            "name": offer.get("name") or code,
            "description": offer.get("description") or "",
            "discount_type": offer.get("discount_type") or "percentage",
            "discount_value": float(offer.get("discount_value") or 0),
            "applies_to": offer.get("applies_to") or "all",
            "active": bool(offer.get("active", True)),
            "expires_at": offer.get("expires_at"),
            "category": offer.get("category") or "Custom",
        })
    await db.platform_settings.update_one(
        {"id": OFFERS_DOC},
        {"$set": {"offers": offers, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return offers


async def delete_offer(db, code: str) -> List[Dict[str, Any]]:
    offers = await get_offers(db)
    offers = [o for o in offers if (o.get("code") or "").upper() != code.upper()]
    await db.platform_settings.update_one(
        {"id": OFFERS_DOC},
        {"$set": {"offers": offers, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return offers


async def get_target_pct(db) -> float:
    doc = await db.platform_settings.find_one({"id": TARGETS_DOC}, {"_id": 0})
    return float((doc or {}).get("target_direct_pct", 40))


async def set_target_pct(db, value: float) -> float:
    v = max(0.0, min(100.0, float(value)))
    await db.platform_settings.update_one(
        {"id": TARGETS_DOC},
        {"$set": {"target_direct_pct": v, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return v


async def get_content_overrides(db) -> Dict[str, Any]:
    doc = await db.platform_settings.find_one({"id": CONTENT_DOC}, {"_id": 0})
    return (doc or {}).get("content", {})


async def set_content_for(db, audience_key: str, content: Dict[str, Any]) -> Dict[str, Any]:
    current = await get_content_overrides(db)
    current[audience_key] = content
    await db.platform_settings.update_one(
        {"id": CONTENT_DOC},
        {"$set": {"content": current, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return current


# ---------------------------------------------------------------------------
# Audience builders
# ---------------------------------------------------------------------------

def build_audience(audience_key: str, guests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    aud = AUDIENCES.get(audience_key)
    if not aud:
        return []
    filtered = [g for g in guests if aud["predicate"](g)]
    filtered.sort(key=aud["sort_key"])
    return filtered


def _portfolio_avg_booking_value(guests: List[Dict[str, Any]]) -> float:
    vals = [g.get("avg_booking_value") or 0 for g in guests if (g.get("total_stays") or 0) > 0]
    return float(statistics.mean(vals)) if vals else 0.0


async def list_campaign_briefs(db) -> List[Dict[str, Any]]:
    cursor = db.guests.find({}, {"_id": 0})
    guests = await cursor.to_list(length=100000)
    content = await get_content_overrides(db)
    offers = await get_offers(db)
    offers_by_code = {o["code"]: o for o in offers}

    avg_value = _portfolio_avg_booking_value(guests)
    briefs = []
    for key, aud in AUDIENCES.items():
        audience = build_audience(key, guests)
        size = len(audience)
        conv = aud["conversion_rate"]
        opportunity = round(size * avg_value * conv, 2) if avg_value else 0.0
        offer = offers_by_code.get(aud["recommended_offer"])
        briefs.append({
            "key": key,
            "name": aud["name"],
            "description": aud["description"],
            "tab": aud["tab"],
            "goal": aud["goal"],
            "campaign_type": aud["campaign_type"],
            "recommended_offer": aud["recommended_offer"],
            "offer_detail": offer,
            "send_timing": aud["send_timing"],
            "conversion_rate": conv,
            "audience_size": size,
            "estimated_opportunity": opportunity,
            "content": content.get(key) or _default_content_for(key, aud),
        })
    return briefs


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def audience_csv_rows(audience_key: str, guests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    aud = AUDIENCES.get(audience_key)
    if not aud:
        return []
    rec_offer = aud["recommended_offer"]
    audience = build_audience(audience_key, guests)
    rows = []
    for g in audience:
        rows.append({
            "first_name": g.get("first_name", ""),
            "last_name": g.get("last_name", ""),
            "email": g.get("email", ""),
            "primary_source": g.get("most_used_source") or g.get("primary_channel") or "",
            "total_stays": g.get("total_stays", 0),
            "last_stay_date": g.get("last_stay_date") or "",
            "lifetime_spend": g.get("lifetime_spend", 0),
            "direct_conversion_score": g.get("direct_conversion_score", 0),
            "rebooking_score": g.get("rebooking_score", 0),
            "revenue_opportunity_score": g.get("revenue_opportunity_score", 0),
            "segments": "; ".join(g.get("segments") or []),
            "recommended_offer_code": rec_offer,
            "cancellation_count": g.get("cancellation_count", 0),
            "remarketing_priority_score": g.get("remarketing_priority_score", 0),
        })
    return rows


CSV_FIELDS = [
    "first_name", "last_name", "email", "primary_source", "total_stays",
    "last_stay_date", "lifetime_spend", "direct_conversion_score",
    "rebooking_score", "revenue_opportunity_score", "segments",
    "recommended_offer_code", "cancellation_count", "remarketing_priority_score",
]


# ---------------------------------------------------------------------------
# Direct booking growth tracker
# ---------------------------------------------------------------------------

def _direct_pct_in_window(reservations: List[Dict[str, Any]], months_back_start: float, months_back_end: float) -> float:
    """Return direct booking % for [now-months_back_start, now-months_back_end] window."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    direct = 0
    total = 0
    for r in reservations:
        if r.get("is_cancelled"):
            continue
        ci = r.get("checkin_date")
        if not ci:
            continue
        try:
            d = datetime.fromisoformat(ci)
        except Exception:
            continue
        months_back = (now - d).days / 30.4375
        if months_back_end <= months_back <= months_back_start:
            total += 1
            if channel_of(r.get("classified_source") or "") == "Direct":
                direct += 1
    return round(direct / total * 100, 1) if total else 0.0


async def growth_tracker(db) -> Dict[str, Any]:
    target_pct = await get_target_pct(db)
    res_cursor = db.reservations.find({}, {"_id": 0})
    reservations = await res_cursor.to_list(length=200000)
    g_cursor = db.guests.find({}, {"_id": 0})
    guests = await g_cursor.to_list(length=100000)

    # Current = last 12 months
    current_pct = _direct_pct_in_window(reservations, 12, 0)
    three_mo_pct = _direct_pct_in_window(reservations, 6, 3)
    six_mo_pct = _direct_pct_in_window(reservations, 9, 6)

    # Annual OTA commission (sum non-cancelled OTA in last 12 mo)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    annual_commission = 0.0
    for r in reservations:
        if r.get("is_cancelled"):
            continue
        if (r.get("classified_source") or "") not in OTA_SOURCES:
            continue
        ci = r.get("checkin_date")
        if not ci:
            continue
        try:
            d = datetime.fromisoformat(ci)
        except Exception:
            continue
        if (now - d).days <= 365:
            annual_commission += float(r.get("estimated_commission_cost") or 0)

    # If we lift direct pct from current to target, est savings:
    # delta_pp / current_ota_pp * annual_commission
    current_ota_pct = 100.0 - current_pct
    delta = target_pct - current_pct
    estimated_savings = 0.0
    if delta > 0 and current_ota_pct > 0:
        estimated_savings = round(annual_commission * (delta / current_ota_pct), 2)

    # High priority audience
    high_audience = build_audience("ota_conversion_high", guests)
    avg_value = _portfolio_avg_booking_value(guests)
    high_opportunity = round(len(high_audience) * avg_value * AUDIENCES["ota_conversion_high"]["conversion_rate"], 2)

    return {
        "current_direct_pct": current_pct,
        "three_months_ago_pct": three_mo_pct,
        "six_months_ago_pct": six_mo_pct,
        "target_direct_pct": target_pct,
        "progress_pct": round(min(100, (current_pct / target_pct * 100) if target_pct else 0), 1),
        "annual_ota_commission": round(annual_commission, 2),
        "estimated_annual_savings_if_target_hit": estimated_savings,
        "high_priority_audience_size": len(high_audience),
        "high_priority_estimated_opportunity": high_opportunity,
    }
