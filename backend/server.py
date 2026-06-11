from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import io
import re
import logging
import uuid
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Any, Dict
from datetime import datetime, timezone, date

import pandas as pd

from segmentation_service import (
    recompute_all_guests,
    list_segment_definitions,
)
from cancellation_service import (
    build_cancellation_summary,
    list_cancelled_reservations,
    export_cancellations_csv,
)
from scoring_service import (
    recalculate_all_scores,
    get_commission_rates,
    set_commission_rates,
    ensure_commission_settings,
    apply_commission_costs,
    commission_summary_by_source,
    estimated_savings_if_top_converted,
    DEFAULT_COMMISSION_RATES,
)
from analytics_service import (
    resolve_date_range,
    filter_reservations,
    revenue_metrics,
    booking_metrics,
    guest_metrics,
    conversion_metrics,
    clv_metrics,
)
from digest_service import (
    ensure_digest_settings,
    update_digest_settings,
    rotate_webhook_token,
    preview_digest,
    run_digest,
    list_digest_log,
    DAY_NAMES,
)
from campaign_service import (
    AUDIENCES,
    TABS,
    CSV_FIELDS,
    ensure_campaign_settings,
    list_campaign_briefs,
    build_audience,
    audience_csv_rows,
    get_offers,
    upsert_offer,
    delete_offer,
    get_target_pct,
    set_target_pct,
    get_content_overrides,
    set_content_for,
    growth_tracker,
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="STR Booking Analytics API")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Booking source classification
# ---------------------------------------------------------------------------

SOURCE_CATEGORIES = [
    "Airbnb",
    "Booking.com",
    "Stayz",
    "VRBO",
    "Expedia",
    "Other OTA",
    "Direct — Website",
    "Direct — Phone",
    "Direct — Email",
    "Direct — Repeat Guest",
    "Unknown",
]

# Known "Other OTA" tokens — anything in this set that didn't match the named OTAs.
OTHER_OTA_TOKENS = [
    "agoda", "hotels.com", "trivago", "trip.com", "ctrip", "lastminute",
    "hotwire", "kayak", "priceline", "marriott", "hilton", "ihg",
    "hostelworld", "tripadvisor", "homeaway", "flipkey", "ota",
]


def classify_source(raw: Optional[str]) -> str:
    """Map raw booking source string → standardized category (case-insensitive)."""
    if raw is None:
        return "Unknown"
    text = str(raw).strip().lower()
    if not text:
        return "Unknown"

    # Named OTAs first (most specific)
    if "airbnb" in text:
        return "Airbnb"
    if "booking" in text:  # booking.com, booking_com
        return "Booking.com"
    if "stayz" in text:
        return "Stayz"
    if "vrbo" in text:
        return "VRBO"
    if "expedia" in text:
        return "Expedia"

    # Direct channels — phone before email (email contains 'mail', not 'phone')
    if "phone" in text or "call" in text:
        return "Direct — Phone"
    if "email" in text or "mail" in text:
        return "Direct — Email"
    if "repeat" in text:
        return "Direct — Repeat Guest"
    if "direct" in text or "website" in text or "own site" in text or re.search(r"\bweb\b", text):
        return "Direct — Website"

    # Other recognised OTAs
    for token in OTHER_OTA_TOKENS:
        if token in text:
            return "Other OTA"

    return "Unknown"


# ---------------------------------------------------------------------------
# CSV column normalisation
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = [
    "reservation_id",
    "guest_first_name",
    "guest_last_name",
    "guest_email",
    "property_name",
    "checkin_date",
    "checkout_date",
    "booking_value",
    "raw_booking_source",
    "booking_date",
]

# Accept many likely header variants (lowercased, stripped of non-alphanumerics)
HEADER_ALIASES: Dict[str, List[str]] = {
    "reservation_id": ["reservationid", "bookingreference", "bookingref", "bookingid", "reservationreference", "confirmationcode", "confirmationnumber", "id"],
    "guest_first_name": ["guestfirstname", "firstname", "fname", "guestfirst"],
    "guest_last_name": ["guestlastname", "lastname", "lname", "surname", "guestlast"],
    "guest_email": ["guestemail", "email", "emailaddress", "guestemailaddress"],
    "property_name": ["propertyname", "property", "listing", "listingname", "unit", "unitname"],
    "checkin_date": ["checkindate", "checkin", "arrivaldate", "arrival", "startdate"],
    "checkout_date": ["checkoutdate", "checkout", "departuredate", "departure", "enddate"],
    "nights": ["nights", "numberofnights", "numnights", "lengthofstay", "los"],
    "guest_count": ["guestcount", "numberofguests", "guests", "numguests", "pax", "noofguests"],
    "booking_value": ["bookingvalue", "totalvalue", "totalbookingvalue", "total", "grossamount", "amount", "revenue", "netvalue", "payout"],
    "raw_booking_source": ["bookingsource", "source", "channel", "platform", "rawsource"],
    "booking_date": ["bookingdate", "datebooked", "reservationdate", "createddate", "createdat", "bookedon"],
    "is_cancelled": ["iscancelled", "cancelled", "canceled", "cancellationstatus", "status"],
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def detect_column_mapping(headers: List[str]) -> Dict[str, Optional[str]]:
    """Return mapping of canonical_field -> source header string (or None)."""
    norm_headers = {_norm(h): h for h in headers}
    mapping: Dict[str, Optional[str]] = {}
    for canonical, aliases in HEADER_ALIASES.items():
        found = None
        # exact canonical first
        if _norm(canonical) in norm_headers:
            found = norm_headers[_norm(canonical)]
        else:
            for alias in aliases:
                if alias in norm_headers:
                    found = norm_headers[alias]
                    break
        mapping[canonical] = found
    return mapping


def _parse_date(v: Any) -> Optional[str]:
    if v is None or (isinstance(v, float) and pd.isna(v)) or v == "":
        return None
    try:
        d = pd.to_datetime(v, errors="coerce", dayfirst=False)
        if pd.isna(d):
            return None
        return d.date().isoformat()
    except Exception:
        return None


def _parse_float(v: Any) -> Optional[float]:
    if v is None or v == "" or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        if isinstance(v, str):
            v = re.sub(r"[^0-9.\-]", "", v)
            if v == "" or v == "-" or v == ".":
                return None
        return float(v)
    except Exception:
        return None


def _parse_int(v: Any) -> Optional[int]:
    f = _parse_float(v)
    return int(f) if f is not None else None


def _parse_bool(v: Any) -> bool:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return False
    s = str(v).strip().lower()
    return s in {"y", "yes", "true", "1", "cancelled", "canceled", "cancel"}


def normalise_row(row: Dict[str, Any], mapping: Dict[str, Optional[str]]) -> Dict[str, Any]:
    def get(field: str) -> Any:
        src = mapping.get(field)
        if not src:
            return None
        v = row.get(src)
        if isinstance(v, float) and pd.isna(v):
            return None
        return v

    checkin = _parse_date(get("checkin_date"))
    checkout = _parse_date(get("checkout_date"))
    nights = _parse_int(get("nights"))
    if nights is None and checkin and checkout:
        try:
            nights = (datetime.fromisoformat(checkout).date() - datetime.fromisoformat(checkin).date()).days
        except Exception:
            nights = None

    raw_source = get("raw_booking_source")
    raw_source = str(raw_source) if raw_source is not None else ""

    return {
        "reservation_id": (str(get("reservation_id")).strip() if get("reservation_id") is not None else ""),
        "guest_first_name": (str(get("guest_first_name")).strip() if get("guest_first_name") is not None else ""),
        "guest_last_name": (str(get("guest_last_name")).strip() if get("guest_last_name") is not None else ""),
        "guest_email": (str(get("guest_email")).strip() if get("guest_email") is not None else ""),
        "property_name": (str(get("property_name")).strip() if get("property_name") is not None else ""),
        "checkin_date": checkin,
        "checkout_date": checkout,
        "nights": nights,
        "guest_count": _parse_int(get("guest_count")),
        "booking_value": _parse_float(get("booking_value")) or 0.0,
        "raw_booking_source": raw_source,
        "classified_source": classify_source(raw_source),
        "booking_date": _parse_date(get("booking_date")),
        "is_cancelled": _parse_bool(get("is_cancelled")),
    }


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class Reservation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    reservation_id: str
    guest_first_name: str = ""
    guest_last_name: str = ""
    guest_email: str = ""
    property_name: str = ""
    checkin_date: Optional[str] = None
    checkout_date: Optional[str] = None
    nights: Optional[int] = None
    guest_count: Optional[int] = None
    booking_value: float = 0.0
    raw_booking_source: str = ""
    classified_source: str = "Unknown"
    booking_date: Optional[str] = None
    is_cancelled: bool = False
    imported_at: str
    manually_overridden: bool = False


class ImportLog(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    filename: str
    imported_at: str
    total_rows: int
    successful_rows: int
    failed_rows: int
    status: str


class ConfirmImportPayload(BaseModel):
    filename: str
    rows: List[Dict[str, Any]]


class SourceOverridePayload(BaseModel):
    classified_source: str


class PropertyCreate(BaseModel):
    name: str
    notes: Optional[str] = ""


class Property(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    notes: str = ""
    created_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_id(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@api.get("/")
async def root():
    return {"name": "STR Booking Analytics API", "status": "ok"}


@api.get("/sources")
async def list_sources():
    return {"sources": SOURCE_CATEGORIES}


@api.post("/import/preview")
async def import_preview(file: UploadFile = File(...)):
    """Parse uploaded CSV; return all normalised rows + column mapping + validation."""
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")

    contents = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(contents), dtype=str, keep_default_na=False, na_values=[""])
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {e}")

    if df.empty:
        raise HTTPException(status_code=400, detail="CSV is empty")

    headers = list(df.columns)
    mapping = detect_column_mapping(headers)

    missing_required = [f for f in REQUIRED_FIELDS if mapping.get(f) is None]

    raw_rows = df.to_dict(orient="records")
    normalised: List[Dict[str, Any]] = []
    row_errors: List[Dict[str, Any]] = []
    for idx, raw in enumerate(raw_rows):
        try:
            n = normalise_row(raw, mapping)
            if not n["reservation_id"]:
                row_errors.append({"row": idx + 2, "error": "Missing reservation id"})
                continue
            normalised.append(n)
        except Exception as e:
            row_errors.append({"row": idx + 2, "error": str(e)})

    return {
        "filename": file.filename,
        "headers": headers,
        "mapping": mapping,
        "missing_required": missing_required,
        "total_rows": len(raw_rows),
        "valid_rows": len(normalised),
        "row_errors": row_errors[:50],
        "rows": normalised,  # full list (frontend slices preview)
    }


@api.post("/import/confirm")
async def import_confirm(payload: ConfirmImportPayload):
    if not payload.rows:
        raise HTTPException(status_code=400, detail="No rows to import")

    now = _now_iso()
    docs = []
    failed = 0
    for r in payload.rows:
        try:
            rid = str(r.get("reservation_id", "")).strip()
            if not rid:
                failed += 1
                continue
            doc = {
                "id": str(uuid.uuid4()),
                "reservation_id": rid,
                "guest_first_name": r.get("guest_first_name", "") or "",
                "guest_last_name": r.get("guest_last_name", "") or "",
                "guest_email": r.get("guest_email", "") or "",
                "property_name": r.get("property_name", "") or "",
                "checkin_date": r.get("checkin_date"),
                "checkout_date": r.get("checkout_date"),
                "nights": r.get("nights"),
                "guest_count": r.get("guest_count"),
                "booking_value": float(r.get("booking_value") or 0),
                "raw_booking_source": r.get("raw_booking_source", "") or "",
                "classified_source": classify_source(r.get("raw_booking_source", "")),
                "booking_date": r.get("booking_date"),
                "is_cancelled": bool(r.get("is_cancelled", False)),
                "imported_at": now,
                "manually_overridden": False,
            }
            docs.append(doc)
        except Exception as e:
            logger.exception("row failed: %s", e)
            failed += 1

    if docs:
        # Upsert by reservation_id to allow appending without strict duplicates
        for d in docs:
            await db.reservations.update_one(
                {"reservation_id": d["reservation_id"]},
                {"$setOnInsert": d},
                upsert=True,
            )

    # Stage 2: recompute guest profiles + segments after each import
    try:
        await recompute_all_guests(db)
        # Stage 3: scores + OTA commission
        await recalculate_all_scores(db)
    except Exception as e:
        logger.exception("guest recompute failed: %s", e)

    log = {
        "id": str(uuid.uuid4()),
        "filename": payload.filename,
        "imported_at": now,
        "total_rows": len(payload.rows),
        "successful_rows": len(docs),
        "failed_rows": failed,
        "status": "completed" if failed == 0 else ("partial" if docs else "failed"),
    }
    await db.import_logs.insert_one(log.copy())
    return _strip_id(log)


@api.get("/reservations")
async def list_reservations(
    source: Optional[str] = None,
    property_name: Optional[str] = None,
    limit: int = Query(500, le=5000),
):
    q: Dict[str, Any] = {}
    if source and source != "all":
        q["classified_source"] = source
    if property_name and property_name != "all":
        q["property_name"] = property_name
    cursor = db.reservations.find(q, {"_id": 0}).sort("checkin_date", -1).limit(limit)
    items = await cursor.to_list(length=limit)
    return {"items": items, "count": len(items)}


@api.patch("/reservations/{rid}/source")
async def override_source(rid: str, payload: SourceOverridePayload):
    if payload.classified_source not in SOURCE_CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid source category")
    res = await db.reservations.update_one(
        {"id": rid},
        {"$set": {"classified_source": payload.classified_source, "manually_overridden": True}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Reservation not found")
    doc = await db.reservations.find_one({"id": rid}, {"_id": 0})
    # Stage 2: source change may shift segments/scores
    try:
        await recompute_all_guests(db)
        await recalculate_all_scores(db)
    except Exception as e:
        logger.exception("guest recompute failed: %s", e)
    return doc


@api.get("/imports")
async def list_imports():
    cursor = db.import_logs.find({}, {"_id": 0}).sort("imported_at", -1).limit(200)
    items = await cursor.to_list(length=200)
    return {"items": items}


@api.get("/analytics/summary")
async def analytics_summary():
    pipeline_by_source = [
        {"$group": {
            "_id": "$classified_source",
            "bookings": {"$sum": 1},
            "revenue": {"$sum": "$booking_value"},
        }},
    ]
    by_source = []
    async for row in db.reservations.aggregate(pipeline_by_source):
        by_source.append({
            "source": row["_id"] or "Unknown",
            "bookings": row["bookings"],
            "revenue": round(float(row["revenue"] or 0), 2),
        })

    total_bookings = sum(s["bookings"] for s in by_source)
    total_revenue = round(sum(s["revenue"] for s in by_source), 2)

    direct_sources = {"Direct — Website", "Direct — Phone", "Direct — Email", "Direct — Repeat Guest"}
    ota_sources = {"Airbnb", "Booking.com", "Stayz", "VRBO", "Expedia", "Other OTA"}

    direct_bookings = sum(s["bookings"] for s in by_source if s["source"] in direct_sources)
    direct_revenue = sum(s["revenue"] for s in by_source if s["source"] in direct_sources)
    ota_bookings = sum(s["bookings"] for s in by_source if s["source"] in ota_sources)
    ota_revenue = sum(s["revenue"] for s in by_source if s["source"] in ota_sources)

    cancelled = await db.reservations.count_documents({"is_cancelled": True})

    return {
        "total_bookings": total_bookings,
        "total_revenue": total_revenue,
        "cancelled": cancelled,
        "by_source": sorted(by_source, key=lambda x: x["bookings"], reverse=True),
        "split": {
            "direct": {"bookings": direct_bookings, "revenue": round(direct_revenue, 2)},
            "ota": {"bookings": ota_bookings, "revenue": round(ota_revenue, 2)},
        },
    }


# --- Properties --------------------------------------------------------------

@api.get("/properties")
async def list_properties():
    cursor = db.properties.find({}, {"_id": 0}).sort("name", 1)
    items = await cursor.to_list(length=500)
    return {"items": items}


@api.post("/properties")
async def create_property(payload: PropertyCreate):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    existing = await db.properties.find_one({"name": name})
    if existing:
        raise HTTPException(status_code=409, detail="Property already exists")
    doc = {
        "id": str(uuid.uuid4()),
        "name": name,
        "notes": payload.notes or "",
        "created_at": _now_iso(),
    }
    await db.properties.insert_one(doc.copy())
    return _strip_id(doc)


@api.delete("/properties/{pid}")
async def delete_property(pid: str):
    res = await db.properties.delete_one({"id": pid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Stage 2 — Guests, Segments, Cancellations
# ---------------------------------------------------------------------------

async def _guests_by_email() -> Dict[str, Dict[str, Any]]:
    cursor = db.guests.find({}, {"_id": 0})
    items = await cursor.to_list(length=100000)
    return {g["email"]: g for g in items}


@api.post("/guests/recompute")
async def recompute_guests():
    result = await recompute_all_guests(db)
    return result


@api.get("/guests")
async def list_guests(
    segment: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(2000, le=10000),
):
    q: Dict[str, Any] = {}
    if segment and segment != "all":
        q["segments"] = segment
    cursor = db.guests.find(q, {"_id": 0}).sort("lifetime_spend", -1).limit(limit)
    items = await cursor.to_list(length=limit)
    if search:
        s = search.lower().strip()
        items = [
            g for g in items
            if s in (g.get("email") or "").lower()
            or s in (g.get("first_name") or "").lower()
            or s in (g.get("last_name") or "").lower()
        ]
    return {"items": items, "count": len(items)}


@api.get("/guests/{guest_id}")
async def get_guest(guest_id: str):
    # guest_id is the lowercase email
    em = guest_id.lower().strip()
    guest = await db.guests.find_one({"id": em}, {"_id": 0})
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")
    # Fetch this guest's reservations split into completed + cancelled
    cursor = db.reservations.find({"guest_email": em}, {"_id": 0}).sort("checkin_date", -1)
    res_list = await cursor.to_list(length=2000)
    # In case stored emails preserve case
    if not res_list:
        cursor = db.reservations.find(
            {"guest_email": {"$regex": f"^{re.escape(em)}$", "$options": "i"}}, {"_id": 0}
        ).sort("checkin_date", -1)
        res_list = await cursor.to_list(length=2000)
    completed = [r for r in res_list if not r.get("is_cancelled")]
    cancelled = [r for r in res_list if r.get("is_cancelled")]
    return {
        "guest": guest,
        "completed": completed,
        "cancelled": cancelled,
    }


@api.get("/segments")
async def list_segments():
    """Definitions + counts for every segment."""
    defs = list_segment_definitions()
    counts: Dict[str, int] = {d["name"]: 0 for d in defs}
    total_guests = await db.guests.count_documents({})
    async for g in db.guests.find({}, {"segments": 1}):
        for s in g.get("segments") or []:
            counts[s] = counts.get(s, 0) + 1
    unsegmented = await db.guests.count_documents({"segments": {"$size": 0}})
    return {
        "total_guests": total_guests,
        "unsegmented": unsegmented,
        "segments": [
            {**d, "guest_count": counts.get(d["name"], 0)} for d in defs
        ],
    }


@api.get("/cancellations/summary")
async def cancellations_summary():
    res_cursor = db.reservations.find({}, {"_id": 0})
    reservations = await res_cursor.to_list(length=100000)
    guests_map = await _guests_by_email()
    return build_cancellation_summary(reservations, guests_map)


@api.get("/cancellations")
async def cancellations_list(
    segment: Optional[str] = None,
    source: Optional[str] = None,
    property_name: Optional[str] = None,
):
    res_cursor = db.reservations.find({}, {"_id": 0})
    reservations = await res_cursor.to_list(length=100000)
    guests_map = await _guests_by_email()
    rows = list_cancelled_reservations(reservations, guests_map, segment, source, property_name)
    return {"items": rows, "count": len(rows)}


@api.get("/cancellations/export.csv", response_class=PlainTextResponse)
async def cancellations_export(
    segment: Optional[str] = None,
    source: Optional[str] = None,
    property_name: Optional[str] = None,
):
    res_cursor = db.reservations.find({}, {"_id": 0})
    reservations = await res_cursor.to_list(length=100000)
    guests_map = await _guests_by_email()
    rows = list_cancelled_reservations(reservations, guests_map, segment, source, property_name)
    csv_text = export_cancellations_csv(rows)
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="cancellation_audience.csv"'},
    )


# ---------------------------------------------------------------------------
# Stage 3 — Scoring + OTA commission
# ---------------------------------------------------------------------------

class CommissionRatesPayload(BaseModel):
    rates: Dict[str, float]


def _score_color_band(score: int) -> str:
    if score >= 75:
        return "green"
    if score >= 50:
        return "amber"
    return "red"


@api.post("/scores/recalculate")
async def scores_recalculate():
    return await recalculate_all_scores(db)


@api.get("/scores/summary")
async def scores_summary():
    g_cursor = db.guests.find({}, {"_id": 0})
    guests = await g_cursor.to_list(length=100000)
    res_cursor = db.reservations.find({}, {"_id": 0})
    reservations = await res_cursor.to_list(length=200000)

    total = len(guests)
    ota_guests = [g for g in guests if g.get("primary_channel") == "OTA"]
    avg_direct_conv = round(
        sum(g.get("direct_conversion_score", 0) for g in ota_guests) / len(ota_guests), 2
    ) if ota_guests else 0.0
    avg_rebook = round(
        sum(g.get("rebooking_score", 0) for g in guests) / total, 2
    ) if total else 0.0
    total_commission = round(
        sum(
            float(r.get("estimated_commission_cost") or 0)
            for r in reservations
            if not r.get("is_cancelled") and (r.get("classified_source") or "") in {
                "Airbnb", "Booking.com", "Stayz", "VRBO", "Expedia", "Other OTA"
            }
        ),
        2,
    )
    savings_top20 = estimated_savings_if_top_converted(guests, reservations, 20.0)

    return {
        "total_guests_scored": total,
        "ota_guest_count": len(ota_guests),
        "avg_direct_conversion_score": avg_direct_conv,
        "avg_rebooking_score": avg_rebook,
        "total_ota_commission_to_date": total_commission,
        "estimated_savings_top20_direct": savings_top20,
    }


@api.get("/scores/guests")
async def scores_list(
    primary_source: Optional[str] = None,
    min_score: int = 0,
    segment: Optional[str] = None,
    limit: int = Query(2000, le=10000),
):
    q: Dict[str, Any] = {}
    if primary_source and primary_source != "all":
        q["primary_channel"] = primary_source
    if segment and segment != "all":
        q["segments"] = segment
    if min_score > 0:
        q["revenue_opportunity_score"] = {"$gte": min_score}
    cursor = db.guests.find(q, {"_id": 0}).sort("revenue_opportunity_score", -1).limit(limit)
    items = await cursor.to_list(length=limit)
    return {"items": items, "count": len(items)}


@api.get("/scores/guests/export.csv", response_class=PlainTextResponse)
async def scores_export(
    primary_source: Optional[str] = None,
    min_score: int = 0,
    segment: Optional[str] = None,
):
    q: Dict[str, Any] = {}
    if primary_source and primary_source != "all":
        q["primary_channel"] = primary_source
    if segment and segment != "all":
        q["segments"] = segment
    if min_score > 0:
        q["revenue_opportunity_score"] = {"$gte": min_score}
    cursor = db.guests.find(q, {"_id": 0}).sort("revenue_opportunity_score", -1)
    items = await cursor.to_list(length=100000)

    buf = io.StringIO()
    fieldnames = [
        "guest_name", "email", "primary_channel", "total_stays", "lifetime_spend",
        "raw_ltv_value", "direct_conversion_score", "lifetime_value_score",
        "rebooking_score", "revenue_opportunity_score", "segments",
    ]
    import csv as _csv
    w = _csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    for g in items:
        w.writerow({
            "guest_name": f"{g.get('first_name','')} {g.get('last_name','')}".strip(),
            "email": g.get("email", ""),
            "primary_channel": g.get("primary_channel", ""),
            "total_stays": g.get("total_stays", 0),
            "lifetime_spend": g.get("lifetime_spend", 0),
            "raw_ltv_value": g.get("raw_ltv_value", 0),
            "direct_conversion_score": g.get("direct_conversion_score", 0),
            "lifetime_value_score": g.get("lifetime_value_score", 0),
            "rebooking_score": g.get("rebooking_score", 0),
            "revenue_opportunity_score": g.get("revenue_opportunity_score", 0),
            "segments": "; ".join(g.get("segments") or []),
        })
    return PlainTextResponse(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="guest_scores.csv"'},
    )


@api.get("/commissions/summary")
async def commissions_summary():
    res_cursor = db.reservations.find({}, {"_id": 0})
    reservations = await res_cursor.to_list(length=200000)
    by_source = commission_summary_by_source(reservations)
    total = round(sum(b["commission"] for b in by_source), 2)
    total_revenue = round(sum(b["revenue"] for b in by_source), 2)
    total_bookings = sum(b["bookings"] for b in by_source)
    return {
        "by_source": by_source,
        "total_commission": total,
        "total_revenue": total_revenue,
        "total_bookings": total_bookings,
    }


@api.get("/settings/commissions")
async def settings_commissions_get():
    rates = await get_commission_rates(db)
    return {"rates": rates, "defaults": DEFAULT_COMMISSION_RATES}


@api.put("/settings/commissions")
async def settings_commissions_put(payload: CommissionRatesPayload):
    if not payload.rates:
        raise HTTPException(status_code=400, detail="rates is required")
    cleaned = await set_commission_rates(db, payload.rates)
    # Recompute commissions on existing reservations & scores
    await apply_commission_costs(db)
    return {"rates": cleaned}


# ---------------------------------------------------------------------------
# Stage 4 — Analytics + Reports
# ---------------------------------------------------------------------------

async def _load_all_reservations() -> List[Dict[str, Any]]:
    cursor = db.reservations.find({}, {"_id": 0})
    return await cursor.to_list(length=200000)


async def _load_all_guests() -> List[Dict[str, Any]]:
    cursor = db.guests.find({}, {"_id": 0})
    return await cursor.to_list(length=100000)


@api.get("/analytics/revenue")
async def analytics_revenue(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    preset: Optional[str] = None,
    property_name: Optional[str] = None,
):
    start, end = resolve_date_range(start_date, end_date, preset)
    res = await _load_all_reservations()
    scoped = filter_reservations(res, start, end, property_name)
    return {
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        **revenue_metrics(scoped, start, end),
    }


@api.get("/analytics/bookings")
async def analytics_bookings(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    preset: Optional[str] = None,
    property_name: Optional[str] = None,
):
    start, end = resolve_date_range(start_date, end_date, preset)
    res = await _load_all_reservations()
    scoped = filter_reservations(res, start, end, property_name)
    return booking_metrics(scoped)


@api.get("/analytics/guests")
async def analytics_guests(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    preset: Optional[str] = None,
    property_name: Optional[str] = None,
):
    start, end = resolve_date_range(start_date, end_date, preset)
    res = await _load_all_reservations()
    guests = await _load_all_guests()
    scoped = filter_reservations(res, start, end, property_name)
    return guest_metrics(scoped, guests, start, end)


@api.get("/analytics/conversion")
async def analytics_conversion(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    preset: Optional[str] = None,
    property_name: Optional[str] = None,
):
    start, end = resolve_date_range(start_date, end_date, preset)
    res = await _load_all_reservations()
    guests = await _load_all_guests()
    rates = await get_commission_rates(db)
    scoped = filter_reservations(res, start, end, property_name)
    return conversion_metrics(scoped, guests, res, rates)


@api.get("/analytics/clv")
async def analytics_clv(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    preset: Optional[str] = None,
    property_name: Optional[str] = None,
):
    guests = await _load_all_guests()
    return clv_metrics(guests)


# --- Reports ----------------------------------------------------------------

def _csv_response(rows: List[Dict[str, Any]], fieldnames: List[str], filename: str) -> PlainTextResponse:
    import csv as _csv
    buf = io.StringIO()
    w = _csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fieldnames})
    return PlainTextResponse(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


REPORT_DEFS = {
    "full_guest_database": {
        "label": "Full guest database with scores & segments",
        "fields": ["email", "first_name", "last_name", "primary_channel", "most_used_source",
                   "total_stays", "lifetime_spend", "raw_ltv_value",
                   "direct_conversion_score", "lifetime_value_score", "rebooking_score",
                   "revenue_opportunity_score", "remarketing_priority_score",
                   "cancellation_count", "cancellation_rate", "recovered", "segments_joined"],
    },
    "ota_commission_period": {
        "label": "OTA commission cost report for period",
        "fields": ["reservation_id", "guest_email", "property_name", "checkin_date",
                   "classified_source", "booking_value", "commission_rate_used",
                   "estimated_commission_cost"],
    },
    "cancellation_period": {
        "label": "Cancellation report for period",
        "fields": ["reservation_id", "guest_email", "property_name", "checkin_date",
                   "booking_date", "booking_value", "classified_source"],
    },
    "revenue_by_source_period": {
        "label": "Revenue by source report for period",
        "fields": ["source", "bookings", "revenue"],
    },
    "top_conversion_opportunities": {
        "label": "Top OTA conversion opportunity guests (dconv ≥ 60)",
        "fields": ["email", "first_name", "last_name", "most_used_source",
                   "direct_conversion_score", "revenue_opportunity_score",
                   "lifetime_spend", "total_stays"],
    },
    "guests_at_risk_of_churning": {
        "label": "Guests at risk of churning (Direct, last stay >12mo)",
        "fields": ["email", "first_name", "last_name", "most_used_source",
                   "last_stay_date", "total_stays", "lifetime_spend"],
    },
    "high_intent_cancellations": {
        "label": "High-intent cancellation guests",
        "fields": ["email", "first_name", "last_name", "cancellation_count",
                   "remarketing_priority_score", "segments_joined"],
    },
}


@api.get("/reports")
async def reports_index():
    return {"reports": [{"key": k, **v} for k, v in REPORT_DEFS.items()]}


@api.get("/reports/{report_name}/count")
async def reports_count(
    report_name: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    preset: Optional[str] = None,
    property_name: Optional[str] = None,
):
    rows = await _build_report_rows(report_name, start_date, end_date, preset, property_name)
    return {"count": len(rows)}


@api.get("/reports/{report_name}.csv", response_class=PlainTextResponse)
async def reports_csv(
    report_name: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    preset: Optional[str] = None,
    property_name: Optional[str] = None,
):
    if report_name not in REPORT_DEFS:
        raise HTTPException(status_code=404, detail="Unknown report")
    rows = await _build_report_rows(report_name, start_date, end_date, preset, property_name)
    fields = REPORT_DEFS[report_name]["fields"]
    return _csv_response(rows, fields, f"{report_name}.csv")


async def _build_report_rows(
    report_name: str,
    start_date: Optional[str],
    end_date: Optional[str],
    preset: Optional[str],
    property_name: Optional[str],
) -> List[Dict[str, Any]]:
    if report_name not in REPORT_DEFS:
        raise HTTPException(status_code=404, detail="Unknown report")
    start, end = resolve_date_range(start_date, end_date, preset)

    if report_name == "full_guest_database":
        guests = await _load_all_guests()
        rows = []
        for g in guests:
            row = {**g}
            row["segments_joined"] = "; ".join(g.get("segments") or [])
            rows.append(row)
        return rows

    if report_name == "ota_commission_period":
        res = await _load_all_reservations()
        scoped = filter_reservations(res, start, end, property_name)
        return [
            r for r in scoped
            if (r.get("classified_source") or "") in {"Airbnb","Booking.com","Stayz","VRBO","Expedia","Other OTA"}
            and not r.get("is_cancelled")
        ]

    if report_name == "cancellation_period":
        res = await _load_all_reservations()
        scoped = filter_reservations(res, start, end, property_name)
        return [r for r in scoped if r.get("is_cancelled")]

    if report_name == "revenue_by_source_period":
        res = await _load_all_reservations()
        scoped = filter_reservations(res, start, end, property_name)
        agg = revenue_metrics(scoped, start, end)
        return agg["revenue_by_source"]

    if report_name == "top_conversion_opportunities":
        guests = await _load_all_guests()
        return [
            g for g in guests
            if (g.get("direct_conversion_score") or 0) >= 60
            and g.get("primary_channel") == "OTA"
        ]

    if report_name == "guests_at_risk_of_churning":
        guests = await _load_all_guests()
        return [
            g for g in guests
            if "Direct Guest at Risk of Churning" in (g.get("segments") or [])
        ]

    if report_name == "high_intent_cancellations":
        guests = await _load_all_guests()
        out = [
            {**g, "segments_joined": "; ".join(g.get("segments") or [])}
            for g in guests
            if "Cancelled — High Intent" in (g.get("segments") or [])
        ]
        out.sort(key=lambda g: g.get("remarketing_priority_score") or 0, reverse=True)
        return out

    return []


# ---------------------------------------------------------------------------
# Stage 4.5 — Weekly digest (Resend)
# ---------------------------------------------------------------------------

class DigestSettingsPayload(BaseModel):
    recipients: Optional[List[str]] = None
    send_day: Optional[int] = None
    send_hour: Optional[int] = None
    send_minute: Optional[int] = None
    timezone: Optional[str] = None
    enabled: Optional[bool] = None


def _dashboard_base() -> str:
    return os.environ.get("DASHBOARD_BASE", "").rstrip("/") or "https://example.com"


@api.get("/settings/digest")
async def settings_digest_get():
    cfg = await ensure_digest_settings(db)
    webhook_url = f"{_dashboard_base()}/api/digest/run?token={cfg.get('webhook_token','')}"
    return {
        "config": {k: v for k, v in cfg.items() if k != "_id"},
        "webhook_url": webhook_url,
        "days_of_week": DAY_NAMES,
        "sender_email": os.environ.get("SENDER_EMAIL", ""),
    }


@api.put("/settings/digest")
async def settings_digest_put(payload: DigestSettingsPayload):
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    cfg = await update_digest_settings(db, patch)
    return {k: v for k, v in cfg.items() if k != "_id"}


@api.post("/settings/digest/rotate-token")
async def settings_digest_rotate():
    token = await rotate_webhook_token(db)
    webhook_url = f"{_dashboard_base()}/api/digest/run?token={token}"
    return {"webhook_token": token, "webhook_url": webhook_url}


@api.get("/digest/preview")
async def digest_preview():
    return await preview_digest(db, _dashboard_base())


class DigestRunPayload(BaseModel):
    force: bool = False
    test_recipient: Optional[str] = None


@api.post("/digest/send-now")
async def digest_send_now(payload: DigestRunPayload):
    """Manual trigger from the UI. Always force-sends; ignores 'no new data' guard."""
    return await run_digest(
        db,
        _dashboard_base(),
        force=True,
        test_recipient=payload.test_recipient,
    )


@api.post("/digest/run", response_class=PlainTextResponse)
async def digest_webhook_run(token: str = Query(...)):
    """Webhook endpoint for cron-job.org. Skips silently if no new data."""
    cfg = await ensure_digest_settings(db)
    expected = cfg.get("webhook_token", "")
    if not expected or token != expected:
        raise HTTPException(status_code=401, detail="Invalid token")
    result = await run_digest(db, _dashboard_base(), force=False)
    status = result.get("status", "unknown")
    detail = result.get("reason") or result.get("error") or result.get("email_id") or ""
    return PlainTextResponse(content=f"{status}: {detail}\n")


@api.get("/digest/history")
async def digest_history():
    items = await list_digest_log(db, limit=30)
    return {"items": items}


# ---------------------------------------------------------------------------
# Stage 5 — Campaign engine
# ---------------------------------------------------------------------------

class OfferPayload(BaseModel):
    code: str
    name: Optional[str] = None
    description: Optional[str] = None
    discount_type: Optional[str] = "percentage"
    discount_value: Optional[float] = 0
    applies_to: Optional[str] = "all"
    active: Optional[bool] = True
    expires_at: Optional[str] = None
    category: Optional[str] = "Custom"


class TargetPayload(BaseModel):
    target_direct_pct: float


class ContentPayload(BaseModel):
    subject_lines: List[str]
    sms: str
    key_points: List[str]
    tone: str
    send_timing: str


@api.get("/campaigns")
async def campaigns_list():
    briefs = await list_campaign_briefs(db)
    grouped: Dict[str, List[Dict[str, Any]]] = {t: [] for t in TABS}
    for b in briefs:
        grouped.setdefault(b["tab"], []).append(b)
    return {"tabs": TABS, "briefs": briefs, "grouped": grouped}


@api.get("/campaigns/growth-tracker")
async def campaigns_growth_tracker():
    return await growth_tracker(db)


@api.get("/campaigns/{key}/guests")
async def campaigns_guests(key: str, limit: int = Query(2000, le=10000)):
    if key not in AUDIENCES:
        raise HTTPException(status_code=404, detail="Unknown audience")
    cursor = db.guests.find({}, {"_id": 0})
    guests = await cursor.to_list(length=100000)
    audience = build_audience(key, guests)
    return {"key": key, "count": len(audience), "items": audience[:limit]}


@api.get("/campaigns/{key}/export.csv", response_class=PlainTextResponse)
async def campaigns_export(key: str):
    if key not in AUDIENCES:
        raise HTTPException(status_code=404, detail="Unknown audience")
    cursor = db.guests.find({}, {"_id": 0})
    guests = await cursor.to_list(length=100000)
    rows = audience_csv_rows(key, guests)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    filename = f"campaign_{key}_{date_str}.csv"
    return _csv_response(rows, CSV_FIELDS, filename)


@api.put("/settings/direct-target")
async def settings_direct_target_put(payload: TargetPayload):
    v = await set_target_pct(db, payload.target_direct_pct)
    return {"target_direct_pct": v}


@api.get("/settings/offers")
async def settings_offers_get():
    offers = await get_offers(db)
    return {"offers": offers}


@api.post("/settings/offers")
async def settings_offers_post(payload: OfferPayload):
    try:
        offers = await upsert_offer(db, payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"offers": offers}


@api.put("/settings/offers/{code}")
async def settings_offers_put(code: str, payload: OfferPayload):
    payload.code = code
    try:
        offers = await upsert_offer(db, payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"offers": offers}


@api.delete("/settings/offers/{code}")
async def settings_offers_delete(code: str):
    offers = await delete_offer(db, code)
    return {"offers": offers}


@api.get("/settings/campaign-content/{key}")
async def settings_campaign_content_get(key: str):
    if key not in AUDIENCES:
        raise HTTPException(status_code=404, detail="Unknown audience")
    content = await get_content_overrides(db)
    return {"key": key, "content": content.get(key)}


@api.put("/settings/campaign-content/{key}")
async def settings_campaign_content_put(key: str, payload: ContentPayload):
    if key not in AUDIENCES:
        raise HTTPException(status_code=404, detail="Unknown audience")
    content = await set_content_for(db, key, payload.model_dump())
    return {"key": key, "content": content.get(key)}




# ---------------------------------------------------------------------------
# Wire up
# ---------------------------------------------------------------------------

app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_seed():
    try:
        await ensure_commission_settings(db)
        await ensure_digest_settings(db)
        await ensure_campaign_settings(db)
    except Exception as e:
        logger.exception("startup seed failed: %s", e)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
