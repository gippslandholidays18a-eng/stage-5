"""Stage 2 backend regression: guests, segments, cancellations endpoints."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://str-analytics-core.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module", autouse=True)
def ensure_recompute(client):
    # Trigger a fresh recompute so tests are deterministic regardless of prior state
    r = client.post(f"{BASE_URL}/api/guests/recompute")
    assert r.status_code == 200, r.text
    return r.json()


# --- /api/guests/recompute ---
class TestRecompute:
    def test_returns_expected_shape(self, client):
        r = client.post(f"{BASE_URL}/api/guests/recompute")
        assert r.status_code == 200
        data = r.json()
        for key in ("guest_count", "context", "updated_at"):
            assert key in data
        assert data["guest_count"] == 10
        assert isinstance(data["context"], dict)
        assert "lifetime_spend_p75" in data["context"]
        assert "cancelled_value_median" in data["context"]


# --- /api/guests ---
class TestGuestsList:
    def test_list_all(self, client):
        r = client.get(f"{BASE_URL}/api/guests")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 10
        sample = data["items"][0]
        for field in [
            "email", "first_name", "last_name", "total_stays", "lifetime_spend",
            "primary_channel", "segments", "remarketing_priority_score",
            "cancellation_count", "cancellation_rate", "properties",
            "first_stay_date", "last_stay_date", "most_used_source", "recovered",
        ]:
            assert field in sample, f"missing field: {field}"

    def test_filter_by_segment(self, client):
        r = client.get(f"{BASE_URL}/api/guests", params={"segment": "OTA First-Time Guest"})
        assert r.status_code == 200
        data = r.json()
        emails = {g["email"] for g in data["items"]}
        # Spec: jane/john/sara/lily/ravi
        expected = {"jane@example.com", "john@example.com", "sara@example.com",
                    "lily@example.com", "ravi@example.com"}
        assert expected.issubset(emails), f"missing: {expected - emails}, got: {emails}"

    def test_high_value_direct(self, client):
        r = client.get(f"{BASE_URL}/api/guests", params={"segment": "High Value Direct Guest"})
        emails = {g["email"] for g in r.json()["items"]}
        assert {"mary@example.com", "tom@example.com"}.issubset(emails)

    def test_high_value_ota(self, client):
        r = client.get(f"{BASE_URL}/api/guests", params={"segment": "High Value OTA Guest"})
        emails = {g["email"] for g in r.json()["items"]}
        assert "ravi@example.com" in emails


# --- /api/guests/{email} ---
class TestGuestDetail:
    def test_get_guest_by_email(self, client):
        r = client.get(f"{BASE_URL}/api/guests/jane@example.com")
        assert r.status_code == 200
        data = r.json()
        assert "guest" in data and "completed" in data and "cancelled" in data
        assert data["guest"]["email"] == "jane@example.com"
        assert len(data["completed"]) == 1
        assert len(data["cancelled"]) == 0

    def test_tim_lee_cancellation(self, client):
        r = client.get(f"{BASE_URL}/api/guests/tim@example.com")
        assert r.status_code == 200
        data = r.json()
        assert len(data["cancelled"]) == 1
        assert len(data["completed"]) == 0
        score = data["guest"]["remarketing_priority_score"]
        # Spec says 40-70 (medium band). Other_misc_info says roughly 30-55. Accept 30-70.
        assert 30 <= score <= 70, f"Tim's score {score} not in expected medium band"

    def test_404(self, client):
        r = client.get(f"{BASE_URL}/api/guests/nope@nowhere.com")
        assert r.status_code == 404


# --- /api/segments ---
class TestSegments:
    def test_returns_12_definitions(self, client):
        r = client.get(f"{BASE_URL}/api/segments")
        assert r.status_code == 200
        data = r.json()
        assert "total_guests" in data and "unsegmented" in data
        defs = data["segments"]
        assert len(defs) == 12
        standard = [d for d in defs if d["kind"] == "standard"]
        cancellation = [d for d in defs if d["kind"] == "cancellation"]
        assert len(standard) == 8
        assert len(cancellation) == 4
        for d in defs:
            for k in ("name", "kind", "description", "guest_count"):
                assert k in d

    def test_ota_first_time_count(self, client):
        r = client.get(f"{BASE_URL}/api/segments")
        defs = {d["name"]: d for d in r.json()["segments"]}
        assert defs["OTA First-Time Guest"]["guest_count"] == 5
        assert defs["High Value Direct Guest"]["guest_count"] == 2
        assert defs["High Value OTA Guest"]["guest_count"] >= 1


# --- /api/cancellations/summary ---
class TestCancellationSummary:
    def test_summary_shape(self, client):
        r = client.get(f"{BASE_URL}/api/cancellations/summary")
        assert r.status_code == 200
        data = r.json()
        for k in ("total_cancelled", "total_lost_revenue", "overall_rate",
                 "rate_by_source", "rate_by_property", "monthly_trend",
                 "avg_days_to_cancel", "segment_breakdown"):
            assert k in data
        assert data["total_cancelled"] == 1  # Tim Lee only
        assert data["total_lost_revenue"] == 890.0
        assert data["overall_rate"] == 10.0


# --- /api/cancellations ---
class TestCancellationsList:
    def test_list_cancellations(self, client):
        r = client.get(f"{BASE_URL}/api/cancellations")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 1
        row = data["items"][0]
        for k in ("cancellation_segment", "recovery_status", "days_to_cancel",
                 "remarketing_priority_score", "reservation_id", "guest_email",
                 "booking_value", "classified_source"):
            assert k in row
        assert row["guest_email"] == "tim@example.com"
        assert row["classified_source"] == "VRBO"

    def test_filter_by_source(self, client):
        r = client.get(f"{BASE_URL}/api/cancellations", params={"source": "VRBO"})
        assert r.json()["count"] == 1
        r2 = client.get(f"{BASE_URL}/api/cancellations", params={"source": "Airbnb"})
        assert r2.json()["count"] == 0

    def test_filter_by_property(self, client):
        # Just verifies the param is honoured without crashing
        r = client.get(f"{BASE_URL}/api/cancellations", params={"property_name": "Nonexistent Property"})
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_filter_by_segment(self, client):
        r = client.get(f"{BASE_URL}/api/cancellations", params={"segment": "Cancelled — High Intent"})
        assert r.status_code == 200


# --- /api/cancellations/export.csv ---
class TestCancellationExport:
    def test_export_csv(self, client):
        r = client.get(f"{BASE_URL}/api/cancellations/export.csv")
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert ".csv" in cd
        body = r.text
        for col in ("reservation_id", "guest_email", "cancellation_segment",
                    "remarketing_priority_score", "days_to_cancel"):
            assert col in body
        assert "tim@example.com" in body


# --- Auto-recompute via PATCH /reservations/{id}/source ---
class TestAutoRecompute:
    def test_source_override_triggers_recompute(self, client):
        # Get a reservation id
        rsv = client.get(f"{BASE_URL}/api/reservations").json()["items"]
        # Find john's record
        john = next(r for r in rsv if r["guest_email"] == "john@example.com")
        original_source = john["classified_source"]

        # Switch to a Direct source temporarily
        patch = client.patch(
            f"{BASE_URL}/api/reservations/{john['id']}/source",
            json={"classified_source": "Direct — Website"},
        )
        assert patch.status_code == 200

        guest = client.get(f"{BASE_URL}/api/guests/john@example.com").json()["guest"]
        assert guest["primary_channel"] == "Direct"

        # Revert
        revert = client.patch(
            f"{BASE_URL}/api/reservations/{john['id']}/source",
            json={"classified_source": original_source},
        )
        assert revert.status_code == 200
        guest2 = client.get(f"{BASE_URL}/api/guests/john@example.com").json()["guest"]
        assert guest2["primary_channel"] == "OTA"


# --- Stage 1 regression spot-check ---
class TestStage1Regression:
    def test_root(self, client):
        assert client.get(f"{BASE_URL}/api/").status_code == 200

    def test_sources(self, client):
        data = client.get(f"{BASE_URL}/api/sources").json()
        assert len(data["sources"]) == 11

    def test_analytics_summary(self, client):
        data = client.get(f"{BASE_URL}/api/analytics/summary").json()
        assert data["total_bookings"] == 10
        assert "split" in data

    def test_imports(self, client):
        assert client.get(f"{BASE_URL}/api/imports").status_code == 200

    def test_properties(self, client):
        assert client.get(f"{BASE_URL}/api/properties").status_code == 200
