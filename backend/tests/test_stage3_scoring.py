"""Stage 3 — Scoring engine + OTA commission tracking tests."""
import os
import csv
import io
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fall back to frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                BASE_URL = line.strip().split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api"

OTA_SOURCES = {"Airbnb", "Booking.com", "Stayz", "VRBO", "Expedia", "Other OTA"}


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# --- Stage 1 + 2 regression ---------------------------------------------------

def test_stage1_sources(session):
    r = session.get(f"{API}/sources")
    assert r.status_code == 200
    assert "Airbnb" in r.json()["sources"]


def test_stage1_analytics_summary(session):
    r = session.get(f"{API}/analytics/summary")
    assert r.status_code == 200
    d = r.json()
    assert "total_bookings" in d and "by_source" in d and "split" in d


def test_stage2_segments_list(session):
    r = session.get(f"{API}/segments")
    assert r.status_code == 200
    assert r.json()["total_guests"] > 0


def test_stage2_cancellations_summary(session):
    r = session.get(f"{API}/cancellations/summary")
    assert r.status_code == 200


def test_stage2_guests_list(session):
    r = session.get(f"{API}/guests")
    assert r.status_code == 200
    assert len(r.json()["items"]) >= 10


def test_stage2_guest_by_email(session):
    r = session.get(f"{API}/guests/mary@example.com")
    assert r.status_code == 200
    assert r.json()["guest"]["email"] == "mary@example.com"


# --- Stage 3: /scores/recalculate --------------------------------------------

def test_scores_recalculate(session):
    r = session.post(f"{API}/scores/recalculate")
    assert r.status_code == 200
    d = r.json()
    assert d["guests_scored"] == 10
    assert "context" in d
    ctx = d["context"]
    for k in ("avg_booking_value_median", "los_median", "lead_time_median"):
        assert k in ctx
    assert "raw_ltv_range" in d
    assert len(d["raw_ltv_range"]) == 2


# --- /scores/summary ---------------------------------------------------------

def test_scores_summary(session):
    r = session.get(f"{API}/scores/summary")
    assert r.status_code == 200
    d = r.json()
    for k in ["total_guests_scored", "ota_guest_count", "avg_direct_conversion_score",
             "avg_rebooking_score", "total_ota_commission_to_date", "estimated_savings_top20_direct"]:
        assert k in d
    assert d["total_guests_scored"] == 10
    assert d["ota_guest_count"] >= 1
    assert d["total_ota_commission_to_date"] >= 0


# --- /scores/guests ----------------------------------------------------------

def test_scores_guests_list_sorted(session):
    r = session.get(f"{API}/scores/guests")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 10
    # Sorted by revenue_opportunity_score desc
    scores = [g["revenue_opportunity_score"] for g in items]
    assert scores == sorted(scores, reverse=True)
    # Required fields
    for g in items:
        for k in ("direct_conversion_score", "lifetime_value_score", "rebooking_score",
                  "revenue_opportunity_score", "raw_ltv_value", "predicted_future_stays",
                  "scores_updated_at"):
            assert k in g, f"missing {k} on {g.get('email')}"


def test_scores_filter_primary_source_ota(session):
    r = session.get(f"{API}/scores/guests", params={"primary_source": "OTA"})
    assert r.status_code == 200
    for g in r.json()["items"]:
        assert g["primary_channel"] == "OTA"


def test_scores_filter_primary_source_direct(session):
    r = session.get(f"{API}/scores/guests", params={"primary_source": "Direct"})
    assert r.status_code == 200
    for g in r.json()["items"]:
        assert g["primary_channel"] == "Direct"


def test_scores_filter_min_score(session):
    r = session.get(f"{API}/scores/guests", params={"min_score": 50})
    assert r.status_code == 200
    for g in r.json()["items"]:
        assert g["revenue_opportunity_score"] >= 50


def test_scores_filter_segment(session):
    r = session.get(f"{API}/scores/guests", params={"segment": "High Value Direct Guest"})
    assert r.status_code == 200
    for g in r.json()["items"]:
        assert "High Value Direct Guest" in g.get("segments", [])


# --- /scores/guests/export.csv -----------------------------------------------

def test_scores_export_csv(session):
    r = session.get(f"{API}/scores/guests/export.csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    reader = csv.DictReader(io.StringIO(r.text))
    expected = {"guest_name", "email", "primary_channel", "total_stays", "lifetime_spend",
                "raw_ltv_value", "direct_conversion_score", "lifetime_value_score",
                "rebooking_score", "revenue_opportunity_score", "segments"}
    assert expected.issubset(set(reader.fieldnames or []))
    rows = list(reader)
    assert len(rows) == 10


# --- Score correctness on sample data ----------------------------------------

def _guest(session, email):
    r = session.get(f"{API}/guests/{email}")
    assert r.status_code == 200, f"missing {email}"
    return r.json()["guest"]


def test_mary_wong_direct_perfect_scores(session):
    g = _guest(session, "mary@example.com")
    assert g["primary_channel"] == "Direct"
    assert g["direct_conversion_score"] == 100
    assert g["raw_ltv_value"] == 8400.0, f"raw_ltv={g['raw_ltv_value']}"
    # Mary should be at the top of LTV normalization
    assert g["lifetime_value_score"] == 100
    assert 85 <= g["revenue_opportunity_score"] <= 93, g["revenue_opportunity_score"]


def test_tim_lee_repeat_canceller_zeros(session):
    g = _guest(session, "tim@example.com")
    # Tim: 1 cancellation, 0 completed stays
    assert g["total_stays"] == 0
    assert g["direct_conversion_score"] == 0
    assert g["lifetime_value_score"] == 0
    assert g["rebooking_score"] == 0
    assert g["revenue_opportunity_score"] == 0


def test_ravi_patel_ota_high_value_segment(session):
    g = _guest(session, "ravi@example.com")
    assert g["primary_channel"] == "OTA"
    assert 50 <= g["direct_conversion_score"] <= 70, g["direct_conversion_score"]


# --- Reservation commission fields -------------------------------------------

def test_reservation_commission_fields(session):
    r = session.get(f"{API}/reservations", params={"limit": 5000})
    assert r.status_code == 200
    items = r.json()["items"]
    assert items
    rates_resp = session.get(f"{API}/settings/commissions").json()["rates"]
    for res in items:
        assert "estimated_commission_cost" in res
        assert "commission_rate_used" in res
        src = res.get("classified_source") or ""
        if src in OTA_SOURCES:
            expected_rate = rates_resp.get(src, rates_resp.get("Other OTA"))
            expected_cost = round(float(res.get("booking_value") or 0) * (expected_rate / 100.0), 2)
            assert abs(res["estimated_commission_cost"] - expected_cost) < 0.02, \
                f"{res['reservation_id']} {src}: {res['estimated_commission_cost']} vs {expected_cost}"
            assert abs(res["commission_rate_used"] - expected_rate) < 0.01
        else:
            assert res["estimated_commission_cost"] == 0.0
            assert res["commission_rate_used"] == 0.0


# --- /commissions/summary ----------------------------------------------------

def test_commissions_summary(session):
    r = session.get(f"{API}/commissions/summary")
    assert r.status_code == 200
    d = r.json()
    assert "by_source" in d and "total_commission" in d and "total_revenue" in d and "total_bookings" in d
    for b in d["by_source"]:
        for k in ("source", "bookings", "revenue", "commission", "avg_commission_per_booking"):
            assert k in b


# --- /settings/commissions ---------------------------------------------------

def test_settings_commissions_get_defaults(session):
    r = session.get(f"{API}/settings/commissions")
    assert r.status_code == 200
    d = r.json()
    assert d["defaults"]["Airbnb"] == 15.5
    assert d["defaults"]["Booking.com"] == 13.9
    assert d["defaults"]["Expedia"] == 15.0
    assert d["defaults"]["VRBO"] == 8.0
    assert d["defaults"]["Other OTA"] == 12.0
    for k in d["defaults"]:
        assert k in d["rates"]


def test_settings_commissions_put_roundtrip_airbnb(session):
    # Find an existing reservation and override it to Airbnb so we can verify
    res_resp = session.get(f"{API}/reservations", params={"limit": 5000}).json()["items"]
    # Save the first reservation's current source for revert
    target = res_resp[0]
    original_src = target["classified_source"]
    rid = target["id"]
    bv = target["booking_value"]

    # Override to Airbnb
    r = session.patch(f"{API}/reservations/{rid}/source", json={"classified_source": "Airbnb"})
    assert r.status_code == 200

    # Get current rates, then set Airbnb to 20.0
    current = session.get(f"{API}/settings/commissions").json()["rates"]
    original_airbnb = current.get("Airbnb", 15.5)
    new_rates = {**current, "Airbnb": 20.0}
    r = session.put(f"{API}/settings/commissions", json={"rates": new_rates})
    assert r.status_code == 200
    assert r.json()["rates"]["Airbnb"] == 20.0

    # Verify target reservation now has commission = booking_value * 0.20
    res = session.get(f"{API}/reservations", params={"limit": 5000}).json()["items"]
    after = next(x for x in res if x["id"] == rid)
    assert after["classified_source"] == "Airbnb"
    expected = round(bv * 0.20, 2)
    assert abs(after["estimated_commission_cost"] - expected) < 0.02, \
        f"{after['estimated_commission_cost']} vs {expected}"
    assert abs(after["commission_rate_used"] - 20.0) < 0.01

    # Revert rate + source
    session.put(f"{API}/settings/commissions", json={"rates": {**current, "Airbnb": original_airbnb}})
    session.patch(f"{API}/reservations/{rid}/source", json={"classified_source": original_src})


# --- Auto-trigger: PATCH source rebuilds + rescores --------------------------

def test_patch_source_triggers_score_recompute(session):
    # Find a Direct guest with 1+ stays
    items = session.get(f"{API}/reservations", params={"limit": 5000}).json()["items"]
    # Find a Direct reservation belonging to a guest with primary_channel Direct
    direct_res = next((r for r in items if (r.get("classified_source") or "").startswith("Direct")), None)
    assert direct_res, "no Direct reservation found"
    rid = direct_res["id"]
    original_src = direct_res["classified_source"]
    email = direct_res["guest_email"].lower()

    before = session.get(f"{API}/guests/{email}").json()["guest"]
    before_revop = before["revenue_opportunity_score"]

    # Override to Booking.com
    r = session.patch(f"{API}/reservations/{rid}/source", json={"classified_source": "Booking.com"})
    assert r.status_code == 200

    after = session.get(f"{API}/guests/{email}").json()["guest"]
    after_revop = after["revenue_opportunity_score"]
    # Score should change (Direct=100 → OTA recomputed lower in most cases, but at minimum changes)
    # Revert
    session.patch(f"{API}/reservations/{rid}/source", json={"classified_source": original_src})

    # We expect a change because direct_conversion went from 100 → recomputed OTA score
    assert before_revop != after_revop, \
        f"Expected revenue_opportunity_score to change after source override but got {before_revop}=={after_revop}"
