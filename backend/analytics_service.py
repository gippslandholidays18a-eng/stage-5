"""
Stage 4 — Analytics service.

Pure functions only. server.py loads reservations + guests once and passes
both into each section helper. All section functions take an optional date
filter (already applied) and return chart-ready JSON.

Date filter rule: a reservation belongs to a period when its `checkin_date`
falls in [start, end]. Cancellations are EXCLUDED from revenue metrics by
default but COUNTED separately for cancellation views.
"""

from __future__ import annotations

import calendar
import statistics
from collections import Counter, defaultdict
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from segmentation_service import DIRECT_SOURCES, OTA_SOURCES, channel_of


# ---------------------------------------------------------------------------
# Date helpers + filtering
# ---------------------------------------------------------------------------

def _parse(s: Optional[str]):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _to_date(s: Optional[str]) -> Optional[date]:
    d = _parse(s)
    return d.date() if d else None


def resolve_date_range(
    start_date: Optional[str],
    end_date: Optional[str],
    preset: Optional[str] = None,
) -> Tuple[Optional[date], Optional[date]]:
    today = datetime.now(timezone.utc).date()
    if preset == "30":
        return today - timedelta(days=30), today
    if preset == "90":
        return today - timedelta(days=90), today
    if preset == "365":
        return today - timedelta(days=365), today
    if preset == "all":
        return None, None
    return _to_date(start_date), _to_date(end_date)


def filter_reservations(
    reservations: List[Dict[str, Any]],
    start: Optional[date],
    end: Optional[date],
    property_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    out = []
    for r in reservations:
        d = _to_date(r.get("checkin_date"))
        if start and (not d or d < start):
            continue
        if end and (not d or d > end):
            continue
        if property_name and property_name != "all" and r.get("property_name") != property_name:
            continue
        out.append(r)
    return out


def _month_key(d: Optional[date]) -> Optional[str]:
    if not d:
        return None
    return d.strftime("%Y-%m")


def _month_iter(start: date, end: date) -> List[str]:
    months: List[str] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            m = 1
            y += 1
    return months


# ---------------------------------------------------------------------------
# Section 1 — Revenue
# ---------------------------------------------------------------------------

def revenue_metrics(
    reservations: List[Dict[str, Any]],
    start: Optional[date],
    end: Optional[date],
) -> Dict[str, Any]:
    completed = [r for r in reservations if not r.get("is_cancelled")]

    total_revenue = sum(float(r.get("booking_value") or 0) for r in completed)
    total_commission = sum(float(r.get("estimated_commission_cost") or 0) for r in completed)
    net_revenue = total_revenue - total_commission

    # By source
    by_source: Dict[str, Dict[str, float]] = defaultdict(lambda: {"revenue": 0.0, "bookings": 0})
    for r in completed:
        s = r.get("classified_source") or "Unknown"
        by_source[s]["revenue"] += float(r.get("booking_value") or 0)
        by_source[s]["bookings"] += 1
    revenue_by_source = [
        {"source": s, "revenue": round(v["revenue"], 2), "bookings": int(v["bookings"])}
        for s, v in by_source.items()
    ]
    revenue_by_source.sort(key=lambda x: x["revenue"], reverse=True)

    # OTA platforms only
    ota_only = [b for b in revenue_by_source if b["source"] in OTA_SOURCES]

    # Direct vs OTA split
    direct_rev = sum(b["revenue"] for b in revenue_by_source if b["source"] in DIRECT_SOURCES)
    ota_rev = sum(b["revenue"] for b in revenue_by_source if b["source"] in OTA_SOURCES)

    # By property
    by_prop: Dict[str, float] = defaultdict(float)
    for r in completed:
        by_prop[r.get("property_name") or "—"] += float(r.get("booking_value") or 0)
    revenue_by_property = [{"property": p, "revenue": round(v, 2)} for p, v in by_prop.items()]
    revenue_by_property.sort(key=lambda x: x["revenue"], reverse=True)

    # Avg booking value by source
    avg_by_source = [
        {
            "source": s,
            "avg": round(v["revenue"] / v["bookings"], 2) if v["bookings"] else 0.0,
        }
        for s, v in by_source.items()
    ]
    avg_by_source.sort(key=lambda x: x["avg"], reverse=True)

    # Monthly stacked: OTA vs Direct revenue per month
    months_set: set = set()
    monthly_split: Dict[str, Dict[str, float]] = defaultdict(lambda: {"direct": 0.0, "ota": 0.0})
    for r in completed:
        mk = _month_key(_to_date(r.get("checkin_date")))
        if not mk:
            continue
        months_set.add(mk)
        ch = channel_of(r.get("classified_source") or "")
        if ch == "Direct":
            monthly_split[mk]["direct"] += float(r.get("booking_value") or 0)
        elif ch == "OTA":
            monthly_split[mk]["ota"] += float(r.get("booking_value") or 0)
    monthly_split_data = [
        {
            "month": mk,
            "direct": round(monthly_split[mk]["direct"], 2),
            "ota": round(monthly_split[mk]["ota"], 2),
        }
        for mk in sorted(months_set)
    ]

    # Month-on-month trend (total)
    monthly_total = [
        {"month": d["month"], "revenue": round(d["direct"] + d["ota"], 2)}
        for d in monthly_split_data
    ]

    # Prior year comparison: align previous-year revenue to current-year months
    monthly_with_py: List[Dict[str, Any]] = []
    monthly_lookup = {d["month"]: d["revenue"] for d in monthly_total}
    for d in monthly_total:
        y, m = d["month"].split("-")
        py_key = f"{int(y) - 1:04d}-{m}"
        monthly_with_py.append({
            "month": d["month"],
            "current_year": d["revenue"],
            "prior_year": monthly_lookup.get(py_key, 0.0),
        })

    # Commission by platform (already computed at booking-level)
    commission_by_platform: Dict[str, float] = defaultdict(float)
    for r in completed:
        s = r.get("classified_source") or ""
        if s in OTA_SOURCES:
            commission_by_platform[s] += float(r.get("estimated_commission_cost") or 0)
    commission_by_source = [
        {"source": s, "commission": round(v, 2)}
        for s, v in commission_by_platform.items()
    ]
    commission_by_source.sort(key=lambda x: x["commission"], reverse=True)

    return {
        "total_revenue": round(total_revenue, 2),
        "total_commission": round(total_commission, 2),
        "net_revenue": round(net_revenue, 2),
        "revenue_by_source": revenue_by_source,
        "revenue_by_ota_platform": ota_only,
        "revenue_by_property": revenue_by_property,
        "avg_value_by_source": avg_by_source,
        "split": {
            "direct": round(direct_rev, 2),
            "ota": round(ota_rev, 2),
        },
        "monthly_split": monthly_split_data,
        "monthly_total": monthly_total,
        "monthly_with_py": monthly_with_py,
        "commission_by_source": commission_by_source,
    }


# ---------------------------------------------------------------------------
# Section 2 — Bookings
# ---------------------------------------------------------------------------

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def booking_metrics(reservations: List[Dict[str, Any]]) -> Dict[str, Any]:
    completed = [r for r in reservations if not r.get("is_cancelled")]
    total_bookings = len(completed)
    unique_guests = len({(r.get("guest_email") or "").lower() for r in completed if r.get("guest_email")})

    # By source
    by_source: Dict[str, int] = Counter(r.get("classified_source") or "Unknown" for r in completed)
    bookings_by_source = [{"source": s, "bookings": n} for s, n in by_source.items()]
    bookings_by_source.sort(key=lambda x: x["bookings"], reverse=True)

    # By property
    by_prop: Dict[str, int] = Counter(r.get("property_name") or "—" for r in completed)
    bookings_by_property = [{"property": p, "bookings": n} for p, n in by_prop.items()]
    bookings_by_property.sort(key=lambda x: x["bookings"], reverse=True)

    # Top 10 properties
    top10 = bookings_by_property[:10]

    # Occupancy trend by month — nights booked attributed to check-in month
    monthly_nights: Dict[str, int] = defaultdict(int)
    for r in completed:
        d = _to_date(r.get("checkin_date"))
        if not d:
            continue
        n = r.get("nights") or 0
        try:
            n = int(n)
        except Exception:
            n = 0
        monthly_nights[_month_key(d)] += n
    occupancy_trend = [
        {"month": mk, "nights": monthly_nights[mk]} for mk in sorted(monthly_nights.keys())
    ]

    # Avg LOS by source
    los_by_source: Dict[str, List[int]] = defaultdict(list)
    for r in completed:
        n = r.get("nights")
        if n:
            try:
                los_by_source[r.get("classified_source") or "Unknown"].append(int(n))
            except Exception:
                pass
    avg_los_by_source = [
        {"source": s, "avg_nights": round(statistics.mean(v), 2) if v else 0.0}
        for s, v in los_by_source.items()
    ]
    avg_los_by_source.sort(key=lambda x: x["avg_nights"], reverse=True)

    # Avg lead time by source (booking_date -> checkin_date)
    lead_by_source: Dict[str, List[int]] = defaultdict(list)
    for r in completed:
        b = _to_date(r.get("booking_date"))
        c = _to_date(r.get("checkin_date"))
        if b and c and (c - b).days >= 0:
            lead_by_source[r.get("classified_source") or "Unknown"].append((c - b).days)
    avg_lead_by_source = [
        {"source": s, "avg_days": round(statistics.mean(v), 1) if v else 0.0}
        for s, v in lead_by_source.items()
    ]
    avg_lead_by_source.sort(key=lambda x: x["avg_days"], reverse=True)

    # Check-in day of week distribution
    dow_counts = [0] * 7
    for r in completed:
        d = _to_date(r.get("checkin_date"))
        if d:
            dow_counts[d.weekday()] += 1
    by_dow = [{"day": DAY_NAMES[i], "bookings": dow_counts[i]} for i in range(7)]

    # Seasonal pattern: count by month-of-year (1..12) across all years in scope
    month_year_counts: Dict[int, int] = defaultdict(int)
    for r in completed:
        d = _to_date(r.get("checkin_date"))
        if d:
            month_year_counts[d.month] += 1
    seasonal = [
        {"month": calendar.month_abbr[m], "month_num": m, "bookings": month_year_counts.get(m, 0)}
        for m in range(1, 13)
    ]

    return {
        "total_bookings": total_bookings,
        "unique_guests": unique_guests,
        "bookings_by_source": bookings_by_source,
        "bookings_by_property": bookings_by_property,
        "top_properties": top10,
        "occupancy_trend": occupancy_trend,
        "avg_los_by_source": avg_los_by_source,
        "avg_lead_by_source": avg_lead_by_source,
        "checkin_by_dow": by_dow,
        "seasonal_pattern": seasonal,
    }


# ---------------------------------------------------------------------------
# Section 3 — Guests
# ---------------------------------------------------------------------------

def guest_metrics(
    reservations: List[Dict[str, Any]],
    guests: List[Dict[str, Any]],
    start: Optional[date],
    end: Optional[date],
) -> Dict[str, Any]:
    """Note: reservations is already filtered by date+property; guests is full list."""
    # In-period guest set (unique emails that have a stay in the filtered window)
    in_period_emails: set = set()
    for r in reservations:
        if r.get("is_cancelled"):
            continue
        em = (r.get("guest_email") or "").lower().strip()
        if em:
            in_period_emails.add(em)
    in_period_guests = [g for g in guests if g.get("email") in in_period_emails]

    total_unique = len(in_period_guests)

    # New vs returning in period: a guest is "new" if first_stay_date falls in [start, end]
    new_n, returning_n = 0, 0
    for g in in_period_guests:
        first = _to_date(g.get("first_stay_date"))
        if first and (not start or first >= start) and (not end or first <= end):
            new_n += 1
        else:
            returning_n += 1
    new_vs_returning = [
        {"name": "New guests", "value": new_n},
        {"name": "Returning guests", "value": returning_n},
    ]

    # Repeat booking rate by source — % of guests whose most_used_source = s and total_stays > 1
    by_source_guests: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for g in guests:
        s = g.get("most_used_source") or "Unknown"
        by_source_guests[s].append(g)
    repeat_rate_by_source = []
    for s, gs in by_source_guests.items():
        if not gs:
            continue
        repeaters = [x for x in gs if (x.get("total_stays") or 0) > 1]
        repeat_rate_by_source.append({
            "source": s,
            "guests": len(gs),
            "repeaters": len(repeaters),
            "rate": round(len(repeaters) / len(gs) * 100, 1),
        })
    repeat_rate_by_source.sort(key=lambda x: x["rate"], reverse=True)

    # Segment distribution
    seg_counts: Dict[str, int] = Counter()
    for g in guests:
        for s in g.get("segments") or []:
            seg_counts[s] += 1
    segment_distribution = [{"segment": s, "guests": n} for s, n in seg_counts.items()]
    segment_distribution.sort(key=lambda x: x["guests"], reverse=True)

    # Avg stays per guest by source (most_used_source)
    avg_stays_by_source = []
    for s, gs in by_source_guests.items():
        if not gs:
            continue
        stays = [g.get("total_stays") or 0 for g in gs]
        avg_stays_by_source.append({
            "source": s,
            "avg_stays": round(statistics.mean(stays), 2) if stays else 0.0,
        })
    avg_stays_by_source.sort(key=lambda x: x["avg_stays"], reverse=True)

    # Top 20 guests by lifetime spend
    top_guests = sorted(guests, key=lambda g: g.get("lifetime_spend") or 0, reverse=True)[:20]
    top_guests_rows = [
        {
            "name": f"{g.get('first_name','')} {g.get('last_name','')}".strip(),
            "email": g.get("email", ""),
            "primary_source": g.get("most_used_source") or g.get("primary_channel"),
            "total_stays": g.get("total_stays", 0),
            "lifetime_spend": g.get("lifetime_spend", 0),
        }
        for g in top_guests
    ]

    # Guest acquisition trend — new guests per month (first_stay_date)
    monthly_new: Dict[str, int] = defaultdict(int)
    for g in guests:
        first = _to_date(g.get("first_stay_date"))
        if first:
            monthly_new[_month_key(first)] += 1
    acquisition_trend = [
        {"month": mk, "new_guests": monthly_new[mk]} for mk in sorted(monthly_new.keys())
    ]

    # Histogram of stays per guest (across all guests)
    bins = {"1": 0, "2": 0, "3": 0, "4+": 0}
    for g in guests:
        n = g.get("total_stays") or 0
        if n <= 0:
            continue
        if n == 1:
            bins["1"] += 1
        elif n == 2:
            bins["2"] += 1
        elif n == 3:
            bins["3"] += 1
        else:
            bins["4+"] += 1
    stays_histogram = [{"bucket": k, "guests": v} for k, v in bins.items()]

    return {
        "total_unique_guests": total_unique,
        "new_vs_returning": new_vs_returning,
        "repeat_rate_by_source": repeat_rate_by_source,
        "segment_distribution": segment_distribution,
        "avg_stays_by_source": avg_stays_by_source,
        "top_guests": top_guests_rows,
        "acquisition_trend": acquisition_trend,
        "stays_histogram": stays_histogram,
    }


# ---------------------------------------------------------------------------
# Section 4 — OTA → Direct Conversion analytics
# ---------------------------------------------------------------------------

def conversion_metrics(
    reservations: List[Dict[str, Any]],
    guests: List[Dict[str, Any]],
    all_reservations: List[Dict[str, Any]],
    commission_rates: Dict[str, float],
) -> Dict[str, Any]:
    # Per-guest classified_source history (across ALL their reservations regardless of date filter)
    history_by_email: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in all_reservations:
        em = (r.get("guest_email") or "").lower().strip()
        if em:
            history_by_email[em].append(r)

    # OTA → Direct converters: guest's earliest stay was OTA, has at least one later Direct booking
    converters: List[str] = []
    ota_only: List[str] = []
    for em, history in history_by_email.items():
        completed = [r for r in history if not r.get("is_cancelled") and r.get("checkin_date")]
        if not completed:
            continue
        completed.sort(key=lambda r: r.get("checkin_date") or "")
        first_channel = channel_of(completed[0].get("classified_source") or "")
        if first_channel != "OTA":
            continue
        later_direct = any(
            channel_of(r.get("classified_source") or "") == "Direct"
            for r in completed[1:]
        )
        if later_direct:
            converters.append(em)
        else:
            ota_only.append(em)

    base = len(converters) + len(ota_only)
    conversion_rate = round(len(converters) / base * 100, 1) if base else 0.0

    # Direct booking percentage trend by month (period-scoped reservations)
    monthly_direct: Dict[str, Dict[str, int]] = defaultdict(lambda: {"direct": 0, "total": 0})
    for r in reservations:
        if r.get("is_cancelled"):
            continue
        mk = _month_key(_to_date(r.get("checkin_date")))
        if not mk:
            continue
        monthly_direct[mk]["total"] += 1
        if channel_of(r.get("classified_source") or "") == "Direct":
            monthly_direct[mk]["direct"] += 1
    direct_pct_trend = [
        {
            "month": mk,
            "direct_pct": round(monthly_direct[mk]["direct"] / monthly_direct[mk]["total"] * 100, 1) if monthly_direct[mk]["total"] else 0.0,
        }
        for mk in sorted(monthly_direct.keys())
    ]

    # Commission saved from Direct bookings (in scope)
    # For each Direct booking, hypothetical commission if it had been via Other OTA average
    avg_ota_rate = (
        sum(commission_rates.get(s, 12.0) for s in OTA_SOURCES) / max(1, len(OTA_SOURCES))
    )
    commission_saved = 0.0
    for r in reservations:
        if r.get("is_cancelled"):
            continue
        if channel_of(r.get("classified_source") or "") == "Direct":
            commission_saved += float(r.get("booking_value") or 0) * (avg_ota_rate / 100.0)
    commission_saved = round(commission_saved, 2)

    # Top OTA sources by conversion opportunity (avg direct_conversion_score of their guests)
    by_source_scores: Dict[str, List[int]] = defaultdict(list)
    for g in guests:
        s = g.get("most_used_source") or ""
        if s in OTA_SOURCES:
            by_source_scores[s].append(g.get("direct_conversion_score") or 0)
    top_ota_opportunity = [
        {
            "source": s,
            "avg_score": round(statistics.mean(v), 1) if v else 0.0,
            "guest_count": len(v),
        }
        for s, v in by_source_scores.items()
    ]
    top_ota_opportunity.sort(key=lambda x: x["avg_score"], reverse=True)

    # Score band distribution (revenue_opportunity_score)
    bands = {"high": 0, "medium": 0, "low": 0}
    for g in guests:
        s = g.get("revenue_opportunity_score") or 0
        if s >= 75:
            bands["high"] += 1
        elif s >= 50:
            bands["medium"] += 1
        else:
            bands["low"] += 1
    score_bands = [
        {"band": "High (75-100)", "guests": bands["high"], "color": "#419B72"},
        {"band": "Medium (50-74)", "guests": bands["medium"], "color": "#D9A05B"},
        {"band": "Low (0-49)", "guests": bands["low"], "color": "#E05A50"},
    ]

    # Cancellation rate by source (in scope)
    cancel_by_source_total: Dict[str, int] = Counter()
    cancel_by_source_cancelled: Dict[str, int] = Counter()
    for r in reservations:
        s = r.get("classified_source") or "Unknown"
        cancel_by_source_total[s] += 1
        if r.get("is_cancelled"):
            cancel_by_source_cancelled[s] += 1
    cancel_rate_by_source = [
        {
            "source": s,
            "rate": round(cancel_by_source_cancelled[s] / cancel_by_source_total[s] * 100, 1) if cancel_by_source_total[s] else 0.0,
            "cancelled": cancel_by_source_cancelled[s],
            "total": cancel_by_source_total[s],
        }
        for s in cancel_by_source_total
    ]
    cancel_rate_by_source.sort(key=lambda x: x["rate"], reverse=True)

    # Cancellation trend by month
    monthly_cancel: Dict[str, Dict[str, int]] = defaultdict(lambda: {"cancelled": 0, "total": 0})
    for r in reservations:
        mk = _month_key(_to_date(r.get("checkin_date")))
        if not mk:
            continue
        monthly_cancel[mk]["total"] += 1
        if r.get("is_cancelled"):
            monthly_cancel[mk]["cancelled"] += 1
    cancel_trend = [
        {
            "month": mk,
            "rate": round(monthly_cancel[mk]["cancelled"] / monthly_cancel[mk]["total"] * 100, 1) if monthly_cancel[mk]["total"] else 0.0,
            "cancelled": monthly_cancel[mk]["cancelled"],
        }
        for mk in sorted(monthly_cancel.keys())
    ]

    # Lost revenue in period
    lost_revenue = round(
        sum(float(r.get("booking_value") or 0) for r in reservations if r.get("is_cancelled")),
        2,
    )

    return {
        "ota_to_direct_conversion_rate": conversion_rate,
        "ota_to_direct_converters": len(converters),
        "ota_only_guests": len(ota_only),
        "direct_pct_trend": direct_pct_trend,
        "commission_saved_from_direct": commission_saved,
        "avg_ota_rate_used": round(avg_ota_rate, 2),
        "top_ota_opportunity": top_ota_opportunity,
        "score_bands": score_bands,
        "cancel_rate_by_source": cancel_rate_by_source,
        "cancel_trend": cancel_trend,
        "lost_revenue": lost_revenue,
    }


# ---------------------------------------------------------------------------
# Section 5 — Customer Lifetime Value
# ---------------------------------------------------------------------------

def clv_metrics(guests: List[Dict[str, Any]]) -> Dict[str, Any]:
    spends = [float(g.get("lifetime_spend") or 0) for g in guests if (g.get("total_stays") or 0) > 0]
    if not spends:
        return {
            "avg_clv": 0.0,
            "avg_clv_by_source": [],
            "clv_distribution": [],
            "top25_share": 0.0,
            "top25_revenue": 0.0,
            "total_revenue": 0.0,
            "clv_by_acquisition_year": [],
        }

    avg_clv = round(statistics.mean(spends), 2)

    # By most_used_source
    by_src: Dict[str, List[float]] = defaultdict(list)
    for g in guests:
        if (g.get("total_stays") or 0) > 0:
            by_src[g.get("most_used_source") or "Unknown"].append(float(g.get("lifetime_spend") or 0))
    avg_clv_by_source = [
        {"source": s, "avg_clv": round(statistics.mean(v), 2)}
        for s, v in by_src.items()
    ]
    avg_clv_by_source.sort(key=lambda x: x["avg_clv"], reverse=True)

    # Distribution histogram — 6 bins by raw_ltv_value (or lifetime_spend if no raw)
    values = [
        float(g.get("raw_ltv_value") or g.get("lifetime_spend") or 0)
        for g in guests
        if (g.get("total_stays") or 0) > 0
    ]
    if values:
        lo, hi = min(values), max(values)
        if hi == lo:
            buckets = [{"range": f"${int(lo):,}", "guests": len(values)}]
        else:
            n_bins = 6
            step = (hi - lo) / n_bins
            counts = [0] * n_bins
            for v in values:
                idx = min(n_bins - 1, int((v - lo) / step))
                counts[idx] += 1
            buckets = [
                {
                    "range": f"${int(lo + i*step):,}-${int(lo + (i+1)*step):,}",
                    "guests": counts[i],
                }
                for i in range(n_bins)
            ]
    else:
        buckets = []

    # Top 25% share
    sorted_spends = sorted(spends, reverse=True)
    top_n = max(1, int(round(len(sorted_spends) * 0.25)))
    top_revenue = sum(sorted_spends[:top_n])
    total = sum(sorted_spends)
    top25_share = round(top_revenue / total * 100, 1) if total else 0.0

    # CLV by acquisition year (cohort)
    cohort_spend: Dict[str, List[float]] = defaultdict(list)
    for g in guests:
        first = _to_date(g.get("first_stay_date"))
        if first and (g.get("total_stays") or 0) > 0:
            cohort_spend[str(first.year)].append(float(g.get("lifetime_spend") or 0))
    clv_by_acquisition_year = [
        {
            "year": y,
            "avg_clv": round(statistics.mean(v), 2),
            "guests": len(v),
        }
        for y, v in sorted(cohort_spend.items())
    ]

    return {
        "avg_clv": avg_clv,
        "avg_clv_by_source": avg_clv_by_source,
        "clv_distribution": buckets,
        "top25_share": top25_share,
        "top25_revenue": round(top_revenue, 2),
        "total_revenue": round(total, 2),
        "clv_by_acquisition_year": clv_by_acquisition_year,
    }
