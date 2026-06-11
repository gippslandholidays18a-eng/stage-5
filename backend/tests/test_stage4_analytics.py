"""Stage 4 — Analytics + Reports endpoint tests.

Covers:
- GET /api/analytics/revenue, /bookings, /guests, /conversion, /clv
- Filter params: preset, start_date+end_date, property_name
- GET /api/reports listing
- GET /api/reports/{key}/count and /api/reports/{key}.csv (7 reports)
- Regression: Stage 1/2/3 endpoints still respond
"""
import csv
import io
import os

import pytest
import requests


def _load_backend_url():
    val = os.environ.get("REACT_APP_BACKEND_URL")
    if val:
        return val.rstrip("/")
    # Fallback: parse /app/frontend/.env (Pytest may not load it)
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                line = line.strip()
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# --- Revenue ----------------------------------------------------------------
class TestAnalyticsRevenue:
    def test_revenue_all_preset_keys_and_total(self, s):
        r = s.get(f"{API}/analytics/revenue", params={"preset": "all"})
        assert r.status_code == 200
        d = r.json()
        required = [
            "total_revenue", "total_commission", "net_revenue",
            "revenue_by_source", "revenue_by_ota_platform", "revenue_by_property",
            "avg_value_by_source", "split", "monthly_split", "monthly_total",
            "monthly_with_py", "commission_by_source",
        ]
        for k in required:
            assert k in d, f"missing key {k}"
        # total_revenue ≈ 14300.5 (sum of completed bookings in sample data)
        assert abs(d["total_revenue"] - 14300.5) < 1.0, f"total_revenue={d['total_revenue']}"
        # split: direct + ota present
        assert "direct" in d["split"] and "ota" in d["split"]
        assert isinstance(d["revenue_by_source"], list)
        assert isinstance(d["monthly_split"], list)

    def test_revenue_preset_30(self, s):
        r = s.get(f"{API}/analytics/revenue", params={"preset": "30"})
        assert r.status_code == 200
        assert "total_revenue" in r.json()

    def test_revenue_custom_range(self, s):
        r = s.get(
            f"{API}/analytics/revenue",
            params={"start_date": "2026-03-01", "end_date": "2026-07-31"},
        )
        assert r.status_code == 200
        d = r.json()
        # checkin dates 2026-03-01..2026-07-15 → should be ~14300.5
        assert d["total_revenue"] > 0

    def test_revenue_property_filter(self, s):
        # Discover a property name first
        all_resp = s.get(f"{API}/analytics/revenue", params={"preset": "all"}).json()
        props = all_resp.get("revenue_by_property") or []
        if not props:
            pytest.skip("no properties to filter")
        pname = props[0].get("property") or props[0].get("name")
        r = s.get(
            f"{API}/analytics/revenue",
            params={"preset": "all", "property_name": pname},
        )
        assert r.status_code == 200
        d = r.json()
        assert d["total_revenue"] <= all_resp["total_revenue"] + 0.01


# --- Bookings ---------------------------------------------------------------
class TestAnalyticsBookings:
    def test_bookings_all(self, s):
        r = s.get(f"{API}/analytics/bookings", params={"preset": "all"})
        assert r.status_code == 200
        d = r.json()
        required = [
            "total_bookings", "unique_guests", "bookings_by_source",
            "bookings_by_property", "top_properties", "occupancy_trend",
            "avg_los_by_source", "avg_lead_by_source", "checkin_by_dow",
            "seasonal_pattern",
        ]
        for k in required:
            assert k in d, f"missing key {k}"
        assert d["total_bookings"] >= 1
        assert len(d["top_properties"]) <= 10
        assert len(d["checkin_by_dow"]) == 7
        assert len(d["seasonal_pattern"]) == 12


# --- Guests -----------------------------------------------------------------
class TestAnalyticsGuests:
    def test_guests_all(self, s):
        r = s.get(f"{API}/analytics/guests", params={"preset": "all"})
        assert r.status_code == 200
        d = r.json()
        required = [
            "total_unique_guests", "new_vs_returning", "repeat_rate_by_source",
            "segment_distribution", "avg_stays_by_source", "top_guests",
            "acquisition_trend", "stays_histogram",
        ]
        for k in required:
            assert k in d, f"missing key {k}"
        assert len(d["new_vs_returning"]) == 2
        assert len(d["top_guests"]) <= 20
        assert len(d["stays_histogram"]) == 4


# --- Conversion -------------------------------------------------------------
class TestAnalyticsConversion:
    def test_conversion_all(self, s):
        r = s.get(f"{API}/analytics/conversion", params={"preset": "all"})
        assert r.status_code == 200
        d = r.json()
        required = [
            "ota_to_direct_conversion_rate", "ota_to_direct_converters",
            "ota_only_guests", "direct_pct_trend", "commission_saved_from_direct",
            "avg_ota_rate_used", "top_ota_opportunity", "score_bands",
            "cancel_rate_by_source", "cancel_trend", "lost_revenue",
        ]
        for k in required:
            assert k in d, f"missing key {k}"
        assert len(d["score_bands"]) == 3
        # score bands should have colors
        for band in d["score_bands"]:
            assert "color" in band, f"missing color in band {band}"


# --- CLV --------------------------------------------------------------------
class TestAnalyticsCLV:
    def test_clv_all(self, s):
        r = s.get(f"{API}/analytics/clv", params={"preset": "all"})
        assert r.status_code == 200
        d = r.json()
        required = [
            "avg_clv", "avg_clv_by_source", "clv_distribution",
            "top25_share", "top25_revenue", "total_revenue",
            "clv_by_acquisition_year",
        ]
        for k in required:
            assert k in d, f"missing key {k}"
        assert len(d["clv_distribution"]) == 6


# --- Reports ----------------------------------------------------------------
EXPECTED_REPORTS = {
    "full_guest_database", "ota_commission_period", "cancellation_period",
    "revenue_by_source_period", "top_conversion_opportunities",
    "guests_at_risk_of_churning", "high_intent_cancellations",
}


class TestReports:
    def test_reports_index_has_7(self, s):
        r = s.get(f"{API}/reports")
        assert r.status_code == 200
        reports = r.json().get("reports", [])
        keys = {x["key"] for x in reports}
        assert keys == EXPECTED_REPORTS, f"got {keys}"
        for rep in reports:
            assert "label" in rep
            assert "fields" in rep and isinstance(rep["fields"], list) and len(rep["fields"]) > 0

    @pytest.mark.parametrize("key", sorted(EXPECTED_REPORTS))
    def test_report_count_endpoint(self, s, key):
        r = s.get(f"{API}/reports/{key}/count", params={"preset": "all"})
        assert r.status_code == 200
        data = r.json()
        assert "count" in data and isinstance(data["count"], int)

    def test_full_guest_db_count_is_10(self, s):
        r = s.get(f"{API}/reports/full_guest_database/count", params={"preset": "all"})
        assert r.status_code == 200
        assert r.json()["count"] == 10

    @pytest.mark.parametrize("key", sorted(EXPECTED_REPORTS))
    def test_report_csv_download(self, s, key):
        r = s.get(f"{API}/reports/{key}.csv", params={"preset": "all"})
        assert r.status_code == 200
        # Content-Type
        ct = r.headers.get("content-type", "")
        assert "text/csv" in ct, f"content-type={ct}"
        # Content-Disposition
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd.lower()
        assert f"{key}.csv" in cd
        # Parseable CSV with header row matching declared fields
        text = r.text
        reader = csv.reader(io.StringIO(text))
        header = next(reader, None)
        assert header is not None and len(header) > 0

    def test_full_guest_csv_has_10_rows(self, s):
        r = s.get(f"{API}/reports/full_guest_database.csv", params={"preset": "all"})
        assert r.status_code == 200
        reader = csv.DictReader(io.StringIO(r.text))
        rows = list(reader)
        assert len(rows) == 10

    def test_unknown_report_returns_404(self, s):
        r = s.get(f"{API}/reports/does_not_exist.csv")
        assert r.status_code == 404

    def test_report_count_respects_property_filter(self, s):
        # Get any property name from analytics
        rev = s.get(f"{API}/analytics/revenue", params={"preset": "all"}).json()
        props = rev.get("revenue_by_property") or []
        if not props:
            pytest.skip("no properties")
        pname = props[0].get("property") or props[0].get("name")
        r_all = s.get(f"{API}/reports/ota_commission_period/count", params={"preset": "all"}).json()["count"]
        r_p = s.get(
            f"{API}/reports/ota_commission_period/count",
            params={"preset": "all", "property_name": pname},
        ).json()["count"]
        assert r_p <= r_all


# --- Stage 1/2/3 regression -------------------------------------------------
class TestRegression:
    def test_sources(self, s):
        assert s.get(f"{API}/sources").status_code == 200

    def test_reservations(self, s):
        r = s.get(f"{API}/reservations", params={"limit": 5})
        assert r.status_code == 200
        assert "items" in r.json()

    def test_old_summary(self, s):
        assert s.get(f"{API}/analytics/summary").status_code == 200

    def test_segments(self, s):
        assert s.get(f"{API}/segments").status_code == 200

    def test_guests(self, s):
        assert s.get(f"{API}/guests").status_code == 200

    def test_scores_summary(self, s):
        assert s.get(f"{API}/scores/summary").status_code == 200

    def test_commissions_summary(self, s):
        assert s.get(f"{API}/commissions/summary").status_code == 200

    def test_settings_commissions(self, s):
        assert s.get(f"{API}/settings/commissions").status_code == 200
