"""STR Booking Analytics backend API tests."""
import os
import io
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else None
if not BASE:
    # Read frontend .env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE = line.split("=", 1)[1].strip()
BASE = BASE.rstrip("/")
API = f"{BASE}/api"

SAMPLE_CSV = open("/tmp/sample.csv", "rb").read()


def test_root():
    r = requests.get(f"{API}/")
    assert r.status_code == 200
    d = r.json()
    assert d["name"] == "STR Booking Analytics API"
    assert d["status"] == "ok"


def test_sources_order():
    r = requests.get(f"{API}/sources")
    assert r.status_code == 200
    expected = ["Airbnb", "Booking.com", "Stayz", "VRBO", "Expedia", "Other OTA",
                "Direct — Website", "Direct — Phone", "Direct — Email",
                "Direct — Repeat Guest", "Unknown"]
    assert r.json()["sources"] == expected


def test_preview_with_sample():
    files = {"file": ("sample.csv", SAMPLE_CSV, "text/csv")}
    r = requests.post(f"{API}/import/preview", files=files)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["valid_rows"] == 10
    assert d["missing_required"] == []
    # check alias detection
    assert d["mapping"]["guest_count"] == "guests"
    assert d["mapping"]["raw_booking_source"] == "booking_source"
    # check classifications by reservation
    by_rid = {r["reservation_id"]: r["classified_source"] for r in d["rows"]}
    expected = {
        "RES-001": "Airbnb",
        "RES-002": "Booking.com",
        "RES-003": "Direct — Website",
        "RES-004": "VRBO",
        "RES-005": "Direct — Phone",
        "RES-006": "Expedia",
        "RES-007": "Stayz",
        "RES-008": "Direct — Email",
        "RES-009": "Other OTA",
        "RES-010": "Direct — Repeat Guest",
    }
    for k, v in expected.items():
        assert by_rid[k] == v, f"{k}: got {by_rid[k]} expected {v}"


def test_classification_random_text_unknown():
    csv = "reservation_id,booking_source,booking_value,checkin_date,checkout_date,guest_first_name,guest_last_name,guest_email,property_name,booking_date\nTEST-UNK,random text xyz,100,2026-08-01,2026-08-03,A,B,a@b.com,X,2026-07-01\n"
    files = {"file": ("u.csv", csv.encode(), "text/csv")}
    r = requests.post(f"{API}/import/preview", files=files)
    assert r.status_code == 200
    assert r.json()["rows"][0]["classified_source"] == "Unknown"


@pytest.fixture(scope="module")
def imported_rows():
    files = {"file": ("sample.csv", SAMPLE_CSV, "text/csv")}
    r = requests.post(f"{API}/import/preview", files=files)
    rows = r.json()["rows"]
    confirm = requests.post(f"{API}/import/confirm", json={"filename": "sample.csv", "rows": rows})
    assert confirm.status_code == 200, confirm.text
    log = confirm.json()
    assert log["successful_rows"] == 10
    assert log["status"] == "completed"
    return rows


def test_confirm_and_list_reservations(imported_rows):
    r = requests.get(f"{API}/reservations")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 10
    # filter by source
    r2 = requests.get(f"{API}/reservations", params={"source": "Airbnb"})
    assert r2.status_code == 200
    abb = r2.json()["items"]
    assert all(it["classified_source"] == "Airbnb" for it in abb)
    assert len(abb) >= 1


def test_append_no_duplicates(imported_rows):
    # Re-import same CSV
    files = {"file": ("sample.csv", SAMPLE_CSV, "text/csv")}
    pv = requests.post(f"{API}/import/preview", files=files).json()
    requests.post(f"{API}/import/confirm", json={"filename": "sample.csv", "rows": pv["rows"]})
    r = requests.get(f"{API}/reservations", params={"limit": 5000})
    rids = [it["reservation_id"] for it in r.json()["items"]]
    # RES-001 should appear only once
    assert rids.count("RES-001") == 1


def test_override_source(imported_rows):
    r = requests.get(f"{API}/reservations", params={"source": "Airbnb"})
    rid = r.json()["items"][0]["id"]
    patch = requests.patch(f"{API}/reservations/{rid}/source", json={"classified_source": "Booking.com"})
    assert patch.status_code == 200, patch.text
    d = patch.json()
    assert d["classified_source"] == "Booking.com"
    assert d["manually_overridden"] is True
    # Verify persisted
    g = requests.get(f"{API}/reservations").json()["items"]
    found = [x for x in g if x["id"] == rid][0]
    assert found["classified_source"] == "Booking.com"
    assert found["manually_overridden"] is True
    # invalid source rejected
    bad = requests.patch(f"{API}/reservations/{rid}/source", json={"classified_source": "Foo"})
    assert bad.status_code == 400


def test_imports_log(imported_rows):
    r = requests.get(f"{API}/imports")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 1
    for it in items:
        assert "total_rows" in it and "successful_rows" in it and "failed_rows" in it and "status" in it
    # sorted desc
    times = [it["imported_at"] for it in items]
    assert times == sorted(times, reverse=True)


def test_analytics_summary(imported_rows):
    r = requests.get(f"{API}/analytics/summary")
    assert r.status_code == 200
    d = r.json()
    assert d["total_bookings"] >= 10
    assert d["total_revenue"] > 0
    assert "split" in d and "direct" in d["split"] and "ota" in d["split"]
    assert d["split"]["direct"]["bookings"] >= 1
    assert d["split"]["ota"]["bookings"] >= 1
    # cancelled count: RES-004 is yes (but it was overridden). Still imports as cancelled true
    assert d["cancelled"] >= 1
    # by_source sorted desc by bookings
    bookings = [x["bookings"] for x in d["by_source"]]
    assert bookings == sorted(bookings, reverse=True)


def test_properties_crud():
    # cleanup any existing
    name = "TEST_Property_Alpha"
    r = requests.post(f"{API}/properties", json={"name": name, "notes": "n"})
    assert r.status_code == 200
    pid = r.json()["id"]
    # dup
    dup = requests.post(f"{API}/properties", json={"name": name})
    assert dup.status_code == 409
    # list
    lst = requests.get(f"{API}/properties").json()["items"]
    assert any(p["id"] == pid for p in lst)
    # delete
    d = requests.delete(f"{API}/properties/{pid}")
    assert d.status_code == 200
    # 404 on second delete
    d2 = requests.delete(f"{API}/properties/{pid}")
    assert d2.status_code == 404
