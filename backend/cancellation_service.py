"""
Cancellation analytics service.

Pure functions that build the /cancellations dashboard from the existing
`reservations` and `guests` collections. No DB writes here — read-only.
"""

from __future__ import annotations

import csv
import io
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from segmentation_service import channel_of, DIRECT_SOURCES, OTA_SOURCES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _days_between(a: Optional[str], b: Optional[str]) -> Optional[int]:
    if not a or not b:
        return None
    try:
        da = datetime.fromisoformat(a).date()
        db_ = datetime.fromisoformat(b).date()
        return (db_ - da).days
    except Exception:
        return None


def _month_key(iso_date: Optional[str]) -> Optional[str]:
    if not iso_date:
        return None
    try:
        return datetime.fromisoformat(iso_date).strftime("%Y-%m")
    except Exception:
        return None


def cancellation_segment_for(reservation: Dict[str, Any], guest: Optional[Dict[str, Any]]) -> str:
    """Pick the most relevant cancellation segment label for a single cancelled reservation."""
    if not guest:
        return "Unsegmented"
    cancel_segments = [s for s in (guest.get("segments") or []) if s.startswith("Cancelled")]
    if not cancel_segments:
        return "Unsegmented"
    # Priority order
    priority = [
        "Cancelled — High Intent",
        "Cancelled — OTA Winback Target",
        "Cancelled — Repeat Canceller",
        "Cancelled — Recovered Guest",
    ]
    for p in priority:
        if p in cancel_segments:
            return p
    return cancel_segments[0]


def _recovery_status_for(guest: Optional[Dict[str, Any]]) -> str:
    if not guest:
        return "—"
    if guest.get("recovered"):
        return "Recovered"
    if guest.get("cancellation_count", 0) >= 2 and guest.get("total_stays", 0) == 0:
        return "Repeat canceller"
    return "Not recovered"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_cancellation_summary(
    reservations: List[Dict[str, Any]],
    guests_by_email: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    total_bookings = len(reservations)
    cancelled = [r for r in reservations if r.get("is_cancelled")]
    total_cancelled = len(cancelled)
    total_lost_revenue = round(sum(float(r.get("booking_value") or 0) for r in cancelled), 2)
    overall_rate = round((total_cancelled / total_bookings) * 100, 2) if total_bookings else 0.0

    # By source — cancellation rate
    by_source_total: Dict[str, int] = Counter()
    by_source_cancelled: Dict[str, int] = Counter()
    for r in reservations:
        s = r.get("classified_source") or "Unknown"
        by_source_total[s] += 1
        if r.get("is_cancelled"):
            by_source_cancelled[s] += 1
    rate_by_source = [
        {
            "source": s,
            "cancelled": by_source_cancelled[s],
            "total": by_source_total[s],
            "rate": round((by_source_cancelled[s] / by_source_total[s]) * 100, 2) if by_source_total[s] else 0.0,
        }
        for s in by_source_total
    ]
    rate_by_source.sort(key=lambda x: x["rate"], reverse=True)

    # By property — cancellation rate
    by_prop_total: Dict[str, int] = Counter()
    by_prop_cancelled: Dict[str, int] = Counter()
    for r in reservations:
        p = r.get("property_name") or "—"
        by_prop_total[p] += 1
        if r.get("is_cancelled"):
            by_prop_cancelled[p] += 1
    rate_by_property = [
        {
            "property": p,
            "cancelled": by_prop_cancelled[p],
            "total": by_prop_total[p],
            "rate": round((by_prop_cancelled[p] / by_prop_total[p]) * 100, 2) if by_prop_total[p] else 0.0,
        }
        for p in by_prop_total
    ]
    rate_by_property.sort(key=lambda x: x["rate"], reverse=True)

    # Monthly trend — count of cancellations by booking_date month (fallback to checkin)
    monthly: Dict[str, int] = defaultdict(int)
    for r in cancelled:
        key = _month_key(r.get("booking_date")) or _month_key(r.get("checkin_date"))
        if key:
            monthly[key] += 1
    monthly_trend = [{"month": m, "cancellations": monthly[m]} for m in sorted(monthly.keys())]

    # Average days between booking date and check-in (proxy for cancel lead time when no explicit cancel date)
    days_by_source: Dict[str, List[int]] = defaultdict(list)
    for r in cancelled:
        d = _days_between(r.get("booking_date"), r.get("checkin_date"))
        if d is not None and d >= 0:
            days_by_source[r.get("classified_source") or "Unknown"].append(d)
    avg_days_to_cancel = [
        {
            "source": s,
            "avg_days": round(statistics.mean(ds), 1) if ds else 0.0,
            "count": len(ds),
        }
        for s, ds in days_by_source.items()
    ]
    avg_days_to_cancel.sort(key=lambda x: x["avg_days"], reverse=True)

    # Segment breakdown of cancelled guests (donut)
    seg_counts: Dict[str, int] = Counter()
    seen_emails: set = set()
    for r in cancelled:
        em = (r.get("guest_email") or "").lower().strip()
        if not em or em in seen_emails:
            continue
        seen_emails.add(em)
        seg = cancellation_segment_for(r, guests_by_email.get(em))
        seg_counts[seg] += 1
    segment_breakdown = [{"segment": s, "guests": n} for s, n in seg_counts.items()]
    segment_breakdown.sort(key=lambda x: x["guests"], reverse=True)

    return {
        "total_cancelled": total_cancelled,
        "total_lost_revenue": total_lost_revenue,
        "overall_rate": overall_rate,
        "rate_by_source": rate_by_source,
        "rate_by_property": rate_by_property,
        "monthly_trend": monthly_trend,
        "avg_days_to_cancel": avg_days_to_cancel,
        "segment_breakdown": segment_breakdown,
    }


def list_cancelled_reservations(
    reservations: List[Dict[str, Any]],
    guests_by_email: Dict[str, Dict[str, Any]],
    segment: Optional[str] = None,
    source: Optional[str] = None,
    property_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    out = []
    for r in reservations:
        if not r.get("is_cancelled"):
            continue
        if source and source != "all" and (r.get("classified_source") or "") != source:
            continue
        if property_name and property_name != "all" and (r.get("property_name") or "") != property_name:
            continue
        em = (r.get("guest_email") or "").lower().strip()
        guest = guests_by_email.get(em)
        seg = cancellation_segment_for(r, guest)
        if segment and segment != "all" and seg != segment:
            continue
        days_to_cancel = _days_between(r.get("booking_date"), r.get("checkin_date"))
        out.append({
            "reservation_id": r.get("reservation_id"),
            "guest_name": f"{r.get('guest_first_name','')} {r.get('guest_last_name','')}".strip(),
            "guest_email": em,
            "property_name": r.get("property_name"),
            "checkin_date": r.get("checkin_date"),
            "booking_date": r.get("booking_date"),
            "booking_value": float(r.get("booking_value") or 0),
            "classified_source": r.get("classified_source"),
            "days_to_cancel": days_to_cancel,
            "cancellation_segment": seg,
            "recovery_status": _recovery_status_for(guest),
            "remarketing_priority_score": (guest or {}).get("remarketing_priority_score", 0),
        })
    out.sort(key=lambda x: x.get("remarketing_priority_score") or 0, reverse=True)
    return out


def export_cancellations_csv(rows: List[Dict[str, Any]]) -> str:
    """Return a CSV string ready for download — the remarketing audience list."""
    buf = io.StringIO()
    fieldnames = [
        "reservation_id",
        "guest_name",
        "guest_email",
        "property_name",
        "checkin_date",
        "booking_date",
        "booking_value",
        "classified_source",
        "days_to_cancel",
        "cancellation_segment",
        "recovery_status",
        "remarketing_priority_score",
    ]
    w = csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fieldnames})
    return buf.getvalue()
