from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, Query
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


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
