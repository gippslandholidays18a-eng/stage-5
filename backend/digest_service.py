"""
Stage 4.5 — Weekly digest service.

Computes "this week vs last week" KPIs, renders an HTML email, and sends via
Resend. The send entry point (`run_digest`) is webhook-callable (cron-job.org)
and is idempotent — it will refuse to send if no new reservations have been
imported since the last successful digest.

Storage:
- platform_settings doc id='digest_config' — recipients, schedule, timezone,
  enabled, webhook_token, last_digest_sent_at, last_skip_reason.
- digest_log collection — every send/skip with status + payload snapshot.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional

import resend

from segmentation_service import DIRECT_SOURCES, OTA_SOURCES, channel_of

CONFIG_ID = "digest_config"
DEFAULT_CONFIG = {
    "id": CONFIG_ID,
    "recipients": [],
    "send_day": 1,        # ISO weekday — 1 = Monday
    "send_hour": 8,
    "send_minute": 0,
    "timezone": "Australia/Sydney",
    "enabled": True,
    "webhook_token": "",
    "last_digest_sent_at": None,
    "last_skip_reason": None,
}

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ---------------------------------------------------------------------------
# Config get/set
# ---------------------------------------------------------------------------

async def ensure_digest_settings(db) -> Dict[str, Any]:
    doc = await db.platform_settings.find_one({"id": CONFIG_ID})
    if doc:
        # Backfill any missing keys (additive defaults)
        changed = False
        for k, v in DEFAULT_CONFIG.items():
            if k not in doc:
                doc[k] = v
                changed = True
        if not doc.get("webhook_token"):
            doc["webhook_token"] = uuid.uuid4().hex
            changed = True
        if changed:
            await db.platform_settings.update_one({"id": CONFIG_ID}, {"$set": doc})
        return doc
    initial = {**DEFAULT_CONFIG, "webhook_token": uuid.uuid4().hex}
    await db.platform_settings.insert_one(initial.copy())
    return initial


async def update_digest_settings(db, patch: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {"recipients", "send_day", "send_hour", "send_minute", "timezone", "enabled"}
    clean = {k: v for k, v in patch.items() if k in allowed}
    if "recipients" in clean:
        clean["recipients"] = [
            (e or "").strip().lower() for e in clean["recipients"] if (e or "").strip()
        ]
    if "send_day" in clean:
        try:
            clean["send_day"] = max(1, min(7, int(clean["send_day"])))
        except Exception:
            clean.pop("send_day", None)
    if "send_hour" in clean:
        try:
            clean["send_hour"] = max(0, min(23, int(clean["send_hour"])))
        except Exception:
            clean.pop("send_hour", None)
    if "send_minute" in clean:
        try:
            clean["send_minute"] = max(0, min(59, int(clean["send_minute"])))
        except Exception:
            clean.pop("send_minute", None)
    await db.platform_settings.update_one(
        {"id": CONFIG_ID}, {"$set": clean}, upsert=True
    )
    return await ensure_digest_settings(db)


async def rotate_webhook_token(db) -> str:
    token = uuid.uuid4().hex
    await db.platform_settings.update_one(
        {"id": CONFIG_ID}, {"$set": {"webhook_token": token}}, upsert=True
    )
    return token


# ---------------------------------------------------------------------------
# KPI computation (this week vs prior week)
# ---------------------------------------------------------------------------

def _to_date(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        return None


def _in_window(d: Optional[date], start: date, end: date) -> bool:
    return d is not None and start <= d <= end


def _pct_change(curr: float, prev: float) -> Optional[float]:
    if prev == 0:
        return None if curr == 0 else float("inf")
    return (curr - prev) / prev * 100.0


def _trend_note(curr: float, prev: float, kind: str = "value") -> str:
    """Plain-English trend note comparing curr to prev."""
    if prev == 0 and curr == 0:
        return "No activity in either week."
    if prev == 0:
        return f"First {kind} recorded in this category — no prior-week baseline."
    pct = (curr - prev) / prev * 100.0
    arrow = "Up" if pct > 0 else ("Down" if pct < 0 else "Unchanged")
    if abs(pct) < 0.5:
        return f"In line with last week ({prev:,.0f} → {curr:,.0f})."
    return f"{arrow} {abs(pct):.0f}% vs last week ({prev:,.0f} → {curr:,.0f})."


def _trend_note_money(curr: float, prev: float) -> str:
    if prev == 0 and curr == 0:
        return "No revenue activity in either week."
    if prev == 0:
        return f"First revenue in this category this period (${curr:,.0f})."
    pct = (curr - prev) / prev * 100.0
    arrow = "Up" if pct > 0 else ("Down" if pct < 0 else "Unchanged")
    if abs(pct) < 0.5:
        return f"Flat vs last week (${prev:,.0f} → ${curr:,.0f})."
    return f"{arrow} {abs(pct):.0f}% vs last week (${prev:,.0f} → ${curr:,.0f})."


def compute_weekly_kpis(reservations: List[Dict[str, Any]], guests: List[Dict[str, Any]]) -> Dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    end = today - timedelta(days=today.weekday() + 1)  # last Sunday
    start = end - timedelta(days=6)                    # last Monday
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=6)

    def slice(res, s, e):
        return [r for r in res if _in_window(_to_date(r.get("checkin_date")), s, e)]

    this_week = slice(reservations, start, end)
    last_week = slice(reservations, prev_start, prev_end)

    # Revenue (completed only)
    this_revenue = sum(float(r.get("booking_value") or 0) for r in this_week if not r.get("is_cancelled"))
    last_revenue = sum(float(r.get("booking_value") or 0) for r in last_week if not r.get("is_cancelled"))

    # OTA vs Direct split (this week)
    direct_rev = sum(
        float(r.get("booking_value") or 0)
        for r in this_week
        if not r.get("is_cancelled") and channel_of(r.get("classified_source") or "") == "Direct"
    )
    ota_rev = sum(
        float(r.get("booking_value") or 0)
        for r in this_week
        if not r.get("is_cancelled") and channel_of(r.get("classified_source") or "") == "OTA"
    )
    total_split = direct_rev + ota_rev
    direct_pct = (direct_rev / total_split * 100.0) if total_split else 0.0
    last_direct = sum(
        float(r.get("booking_value") or 0) for r in last_week
        if not r.get("is_cancelled") and channel_of(r.get("classified_source") or "") == "Direct"
    )
    last_ota = sum(
        float(r.get("booking_value") or 0) for r in last_week
        if not r.get("is_cancelled") and channel_of(r.get("classified_source") or "") == "OTA"
    )
    last_total_split = last_direct + last_ota
    last_direct_pct = (last_direct / last_total_split * 100.0) if last_total_split else 0.0

    # Booking counts
    this_bookings = len([r for r in this_week if not r.get("is_cancelled")])
    last_bookings = len([r for r in last_week if not r.get("is_cancelled")])

    # Cancellations
    this_cancels = [r for r in this_week if r.get("is_cancelled")]
    last_cancels = [r for r in last_week if r.get("is_cancelled")]
    this_cancel_count = len(this_cancels)
    last_cancel_count = len(last_cancels)
    this_lost = sum(float(r.get("booking_value") or 0) for r in this_cancels)
    last_lost = sum(float(r.get("booking_value") or 0) for r in last_cancels)

    # Top performing property this week (by revenue)
    prop_rev: Dict[str, float] = {}
    for r in this_week:
        if r.get("is_cancelled"):
            continue
        prop_rev[r.get("property_name") or "—"] = (
            prop_rev.get(r.get("property_name") or "—", 0) + float(r.get("booking_value") or 0)
        )
    top_property = None
    if prop_rev:
        name, rev = max(prop_rev.items(), key=lambda kv: kv[1])
        top_property = {"property": name, "revenue": round(rev, 2)}

    # Newly flagged high-priority conversion targets:
    # OTA guests with direct_conversion_score >= 60 whose most recent reservation
    # (by checkin_date) falls in this week — proxy for "freshly surfaced"
    this_week_emails = {
        (r.get("guest_email") or "").lower().strip()
        for r in this_week
        if not r.get("is_cancelled") and (r.get("guest_email") or "").strip()
    }
    new_high_priority = []
    for g in guests:
        if g.get("primary_channel") != "OTA":
            continue
        if (g.get("direct_conversion_score") or 0) < 60:
            continue
        if g.get("email") in this_week_emails:
            new_high_priority.append({
                "email": g["email"],
                "name": f"{g.get('first_name','')} {g.get('last_name','')}".strip(),
                "direct_conversion_score": g.get("direct_conversion_score"),
                "revenue_opportunity_score": g.get("revenue_opportunity_score"),
                "most_used_source": g.get("most_used_source"),
            })
    new_high_priority.sort(key=lambda x: x.get("revenue_opportunity_score") or 0, reverse=True)

    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "prior_period": {"start": prev_start.isoformat(), "end": prev_end.isoformat()},
        "kpis": {
            "revenue": {
                "current": round(this_revenue, 2),
                "previous": round(last_revenue, 2),
                "trend": _trend_note_money(this_revenue, last_revenue),
            },
            "direct_share_pct": {
                "current": round(direct_pct, 1),
                "previous": round(last_direct_pct, 1),
                "trend": _direct_split_trend(direct_pct, last_direct_pct),
                "direct_revenue": round(direct_rev, 2),
                "ota_revenue": round(ota_rev, 2),
            },
            "bookings": {
                "current": this_bookings,
                "previous": last_bookings,
                "trend": _trend_note(this_bookings, last_bookings, "booking"),
            },
            "cancellations": {
                "count_current": this_cancel_count,
                "count_previous": last_cancel_count,
                "lost_current": round(this_lost, 2),
                "lost_previous": round(last_lost, 2),
                "trend": _trend_note(this_cancel_count, last_cancel_count, "cancellation"),
            },
            "top_property": top_property,
            "new_high_priority": new_high_priority,
        },
    }


def _direct_split_trend(curr: float, prev: float) -> str:
    diff = curr - prev
    if abs(diff) < 0.1:
        return f"Direct share holding around {curr:.1f}%."
    arrow = "improved" if diff > 0 else "fell"
    return f"Direct share {arrow} from {prev:.1f}% to {curr:.1f}%."


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def _fmt_aud(v) -> str:
    return f"${float(v or 0):,.0f}"


def render_digest_html(kpis_payload: Dict[str, Any], dashboard_base: str) -> str:
    k = kpis_payload["kpis"]
    period = kpis_payload["period"]

    revenue_link = f"{dashboard_base}/?tab=revenue"
    bookings_link = f"{dashboard_base}/?tab=bookings"
    cancel_link = f"{dashboard_base}/cancellations"
    scores_link = f"{dashboard_base}/scores"
    property_link = f"{dashboard_base}/?tab=revenue"

    new_hp = k["new_high_priority"]
    new_hp_html = (
        "<ul style='margin:8px 0 0 0;padding-left:18px;color:#374151;font-size:13px;'>"
        + "".join(
            f"<li><strong>{g['name'] or g['email']}</strong> · score {g['direct_conversion_score']}/100"
            f" · via {g['most_used_source'] or '—'}</li>"
            for g in new_hp[:10]
        )
        + "</ul>"
        if new_hp else
        "<div style='color:#9CA3AF;font-size:13px;margin-top:6px;'>No new high-priority conversion targets this week.</div>"
    )

    top_property_html = (
        f"<div style='font-size:24px;color:#111827;font-weight:600;'>{k['top_property']['property']}</div>"
        f"<div style='color:#6B7280;font-size:13px;margin-top:2px;'>{_fmt_aud(k['top_property']['revenue'])} in revenue</div>"
        if k["top_property"] else
        "<div style='color:#9CA3AF;font-size:14px;'>No property revenue this week.</div>"
    )

    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background-color:#F3F4F6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#111827;">
<table width="100%" cellpadding="0" cellspacing="0" style="background-color:#F3F4F6;padding:32px 0;">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #E5E7EB;">
      <!-- Header -->
      <tr><td style="background-color:#0B0C11;color:#ffffff;padding:28px 32px;">
        <div style="font-size:11px;letter-spacing:3px;text-transform:uppercase;color:#D9A05B;">Sourcebench · Weekly digest</div>
        <div style="font-size:22px;font-weight:600;margin-top:4px;">Week of {period['start']} → {period['end']}</div>
      </td></tr>

      <!-- Revenue -->
      <tr><td style="padding:24px 32px 8px 32px;">
        <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#6B7280;">Total revenue</div>
        <div style="font-size:34px;font-weight:600;color:#111827;margin-top:4px;">{_fmt_aud(k['revenue']['current'])}</div>
        <div style="color:#374151;font-size:13px;margin-top:6px;">{k['revenue']['trend']}</div>
        <a href="{revenue_link}" style="color:#007786;font-size:12px;text-decoration:none;">Open revenue dashboard →</a>
      </td></tr>

      <!-- Direct vs OTA -->
      <tr><td style="padding:20px 32px 8px 32px;border-top:1px solid #F3F4F6;">
        <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#6B7280;">Direct vs OTA split</div>
        <div style="font-size:30px;font-weight:600;color:#007786;margin-top:4px;">{k['direct_share_pct']['current']}% direct</div>
        <div style="color:#374151;font-size:13px;margin-top:6px;">{k['direct_share_pct']['trend']}</div>
        <div style="color:#6B7280;font-size:12px;margin-top:2px;">{_fmt_aud(k['direct_share_pct']['direct_revenue'])} direct · {_fmt_aud(k['direct_share_pct']['ota_revenue'])} OTA</div>
        <a href="{scores_link}" style="color:#007786;font-size:12px;text-decoration:none;">Open conversion view →</a>
      </td></tr>

      <!-- New bookings -->
      <tr><td style="padding:20px 32px 8px 32px;border-top:1px solid #F3F4F6;">
        <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#6B7280;">New bookings</div>
        <div style="font-size:30px;font-weight:600;color:#111827;margin-top:4px;">{k['bookings']['current']:,}</div>
        <div style="color:#374151;font-size:13px;margin-top:6px;">{k['bookings']['trend']}</div>
        <a href="{bookings_link}" style="color:#007786;font-size:12px;text-decoration:none;">Open booking volume →</a>
      </td></tr>

      <!-- Cancellations -->
      <tr><td style="padding:20px 32px 8px 32px;border-top:1px solid #F3F4F6;">
        <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#6B7280;">Cancellations</div>
        <div style="font-size:30px;font-weight:600;color:#E05A50;margin-top:4px;">{k['cancellations']['count_current']:,} <span style="font-size:16px;color:#6B7280;font-weight:400;">({_fmt_aud(k['cancellations']['lost_current'])} lost)</span></div>
        <div style="color:#374151;font-size:13px;margin-top:6px;">{k['cancellations']['trend']}</div>
        <a href="{cancel_link}" style="color:#007786;font-size:12px;text-decoration:none;">Open cancellation intelligence →</a>
      </td></tr>

      <!-- Top property -->
      <tr><td style="padding:20px 32px 8px 32px;border-top:1px solid #F3F4F6;">
        <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#6B7280;">Top performing property</div>
        <div style="margin-top:4px;">{top_property_html}</div>
        <a href="{property_link}" style="color:#007786;font-size:12px;text-decoration:none;">Open revenue by property →</a>
      </td></tr>

      <!-- New high priority -->
      <tr><td style="padding:20px 32px 28px 32px;border-top:1px solid #F3F4F6;">
        <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#6B7280;">New high-priority conversion targets</div>
        {new_hp_html}
        <a href="{scores_link}" style="color:#007786;font-size:12px;text-decoration:none;display:inline-block;margin-top:10px;">Open scores →</a>
      </td></tr>

      <!-- Footer -->
      <tr><td style="background-color:#F9FAFB;padding:18px 32px;color:#9CA3AF;font-size:11px;border-top:1px solid #E5E7EB;">
        Sourcebench · Weekly digest · You're receiving this because your address is on the digest recipient list.
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>"""


# ---------------------------------------------------------------------------
# Send / orchestrate
# ---------------------------------------------------------------------------

async def has_new_data_since(db, since_iso: Optional[str]) -> bool:
    if not since_iso:
        # First run — only send if we have any data at all
        return await db.reservations.count_documents({}) > 0
    return await db.reservations.count_documents({"imported_at": {"$gt": since_iso}}) > 0


async def _load_kpis(db) -> Dict[str, Any]:
    res = await db.reservations.find({}, {"_id": 0}).to_list(length=200000)
    guests = await db.guests.find({}, {"_id": 0}).to_list(length=100000)
    return compute_weekly_kpis(res, guests)


async def preview_digest(db, dashboard_base: str) -> Dict[str, Any]:
    payload = await _load_kpis(db)
    html = render_digest_html(payload, dashboard_base)
    return {"payload": payload, "html": html}


async def run_digest(
    db,
    dashboard_base: str,
    force: bool = False,
    test_recipient: Optional[str] = None,
) -> Dict[str, Any]:
    """Send the weekly digest. Returns a log entry."""
    cfg = await ensure_digest_settings(db)
    now_iso = datetime.now(timezone.utc).isoformat()

    if not cfg.get("enabled") and not force:
        return await _log_skip(db, "disabled", cfg, now_iso)

    if not force and not await has_new_data_since(db, cfg.get("last_digest_sent_at")):
        return await _log_skip(db, "no_new_data", cfg, now_iso)

    recipients = [test_recipient] if test_recipient else (cfg.get("recipients") or [])
    recipients = [r for r in recipients if r]
    if not recipients:
        return await _log_skip(db, "no_recipients", cfg, now_iso)

    payload = await _load_kpis(db)
    html = render_digest_html(payload, dashboard_base)
    period = payload["period"]
    subject = f"Sourcebench weekly digest · {period['start']} → {period['end']}"

    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        return await _log_skip(db, "missing_api_key", cfg, now_iso)
    resend.api_key = api_key

    sender_name = os.environ.get("SENDER_NAME", "Sourcebench Digest")
    sender_email = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")
    params = {
        "from": f"{sender_name} <{sender_email}>",
        "to": recipients,
        "subject": subject,
        "html": html,
    }

    try:
        resp = await asyncio.to_thread(resend.Emails.send, params)
        email_id = resp.get("id") if isinstance(resp, dict) else None
        log = {
            "id": str(uuid.uuid4()),
            "sent_at": now_iso,
            "status": "sent",
            "recipients": recipients,
            "subject": subject,
            "email_id": email_id,
            "period": period,
            "kpis": payload["kpis"],
        }
        await db.digest_log.insert_one(log.copy())
        if not test_recipient:
            await db.platform_settings.update_one(
                {"id": CONFIG_ID},
                {"$set": {"last_digest_sent_at": now_iso, "last_skip_reason": None}},
            )
        log.pop("_id", None)
        return log
    except Exception as e:
        log = {
            "id": str(uuid.uuid4()),
            "sent_at": now_iso,
            "status": "failed",
            "recipients": recipients,
            "subject": subject,
            "error": str(e),
        }
        await db.digest_log.insert_one(log.copy())
        log.pop("_id", None)
        return log


async def _log_skip(db, reason: str, cfg: Dict[str, Any], now_iso: str) -> Dict[str, Any]:
    log = {
        "id": str(uuid.uuid4()),
        "sent_at": now_iso,
        "status": "skipped",
        "reason": reason,
        "recipients": cfg.get("recipients", []),
    }
    await db.digest_log.insert_one(log.copy())
    await db.platform_settings.update_one(
        {"id": CONFIG_ID}, {"$set": {"last_skip_reason": reason}}, upsert=True
    )
    log.pop("_id", None)
    return log


async def list_digest_log(db, limit: int = 20) -> List[Dict[str, Any]]:
    cursor = db.digest_log.find({}, {"_id": 0}).sort("sent_at", -1).limit(limit)
    return await cursor.to_list(length=limit)
