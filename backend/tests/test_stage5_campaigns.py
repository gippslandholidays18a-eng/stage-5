"""Stage 5 — Campaign engine backend tests."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://str-analytics-core.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

EXPECTED_KEYS = {
    "OTA Conversion": ["ota_conversion_high", "ota_conversion_medium", "airbnb_winback", "booking_winback", "stayz_winback"],
    "Guest Retention": ["direct_loyal", "high_value_direct", "direct_at_risk"],
    "Win-Back & Re-engagement": ["cancelled_high_intent", "cancelled_ota_winback", "recovered_guests", "lapsed_all", "single_stay_ota"],
}
ALL_KEYS = [k for ks in EXPECTED_KEYS.values() for k in ks]


@pytest.fixture(scope="module")
def s():
    return requests.Session()


# Stage 5 — /api/campaigns shape
def test_campaigns_list(s):
    r = s.get(f"{API}/campaigns", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert data["tabs"] == ["OTA Conversion", "Guest Retention", "Win-Back & Re-engagement"]
    assert len(data["briefs"]) == 13
    keys = {b["key"] for b in data["briefs"]}
    assert keys == set(ALL_KEYS)
    # validate brief structure
    for b in data["briefs"]:
        for f in ["key","name","description","tab","goal","campaign_type","recommended_offer",
                  "send_timing","conversion_rate","audience_size","estimated_opportunity","content"]:
            assert f in b, f"missing {f} in {b['key']}"
        # content shape
        c = b["content"]
        for cf in ["subject_lines","sms","key_points","tone","send_timing"]:
            assert cf in c
        assert len(c["subject_lines"]) >= 3
    # tab grouping
    for tab, expected in EXPECTED_KEYS.items():
        cards = data["grouped"][tab]
        assert len(cards) == len(expected), f"{tab} has {len(cards)} expected {len(expected)}"
        assert {c["key"] for c in cards} == set(expected)


# Stage 5 — Predicates against sample data
def test_predicates_sample_counts(s):
    r = s.get(f"{API}/campaigns", timeout=30)
    by_key = {b["key"]: b for b in r.json()["briefs"]}
    # spec: ota_conversion_medium=3, high_value_direct=2, single_stay_ota=5
    assert by_key["ota_conversion_medium"]["audience_size"] == 3, f"got {by_key['ota_conversion_medium']['audience_size']}"
    assert by_key["high_value_direct"]["audience_size"] == 2, f"got {by_key['high_value_direct']['audience_size']}"
    assert by_key["single_stay_ota"]["audience_size"] == 5, f"got {by_key['single_stay_ota']['audience_size']}"


# Stage 5 — guests sorted properly
def test_campaign_guests_sorted(s):
    r = s.get(f"{API}/campaigns/single_stay_ota/guests", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert data["key"] == "single_stay_ota"
    assert data["count"] == len(data["items"])
    # sort by direct_conversion_score DESC
    scores = [g.get("direct_conversion_score") or 0 for g in data["items"]]
    assert scores == sorted(scores, reverse=True)
    # lifetime_value_score & direct_conversion_score populated
    for g in data["items"]:
        assert "lifetime_value_score" in g
        assert "direct_conversion_score" in g


def test_high_value_direct_guests_content(s):
    r = s.get(f"{API}/campaigns/high_value_direct/guests", timeout=30)
    assert r.status_code == 200
    items = r.json()["items"]
    names = {g.get("first_name") for g in items}
    # Spec: Mary, Tom
    assert "Mary" in names and "Tom" in names, f"got {names}"


def test_campaigns_guests_unknown_404(s):
    r = s.get(f"{API}/campaigns/nonexistent_key/guests", timeout=30)
    assert r.status_code == 404


# Stage 5 — CSV export
def test_campaign_csv_export(s):
    r = s.get(f"{API}/campaigns/single_stay_ota/export.csv", timeout=30)
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    cd = r.headers.get("content-disposition", "")
    assert "campaign_single_stay_ota_" in cd and ".csv" in cd
    text = r.text
    header_line = text.splitlines()[0]
    cols = [c.strip() for c in header_line.split(",")]
    expected_cols = ["first_name","last_name","email","primary_source","total_stays",
                     "last_stay_date","lifetime_spend","direct_conversion_score","rebooking_score",
                     "revenue_opportunity_score","segments","recommended_offer_code",
                     "cancellation_count","remarketing_priority_score"]
    assert cols == expected_cols, f"got {cols}"


def test_campaign_csv_unknown_404(s):
    r = s.get(f"{API}/campaigns/nope/export.csv", timeout=30)
    assert r.status_code == 404


# Stage 5 — Growth tracker
def test_growth_tracker_shape(s):
    r = s.get(f"{API}/campaigns/growth-tracker", timeout=30)
    assert r.status_code == 200
    data = r.json()
    for f in ["current_direct_pct","three_months_ago_pct","six_months_ago_pct",
              "target_direct_pct","progress_pct","annual_ota_commission",
              "estimated_annual_savings_if_target_hit","high_priority_audience_size",
              "high_priority_estimated_opportunity"]:
        assert f in data, f"missing {f}"
    assert data["target_direct_pct"] == 40


# Stage 5 — direct target PUT/persistence
def test_direct_target_put_and_restore(s):
    r = s.put(f"{API}/settings/direct-target", json={"target_direct_pct": 50}, timeout=30)
    assert r.status_code == 200
    assert r.json()["target_direct_pct"] == 50
    # verify
    g = s.get(f"{API}/campaigns/growth-tracker", timeout=30).json()
    assert g["target_direct_pct"] == 50
    # restore
    r2 = s.put(f"{API}/settings/direct-target", json={"target_direct_pct": 40}, timeout=30)
    assert r2.status_code == 200
    assert r2.json()["target_direct_pct"] == 40


# Stage 5 — Offers CRUD
def test_default_offers(s):
    r = s.get(f"{API}/settings/offers", timeout=30)
    assert r.status_code == 200
    offers = r.json()["offers"]
    codes = {o["code"] for o in offers}
    expected = {"DIRECT10","DIRECT15","EARLYACCESS","FLEXCANCEL","LOYALGUEST","VIP5",
                "REFERRAL20","COMEBACK15","WEVECHANGED","MISSYOU10","OFFSEASON20","LASTMINUTE"}
    assert expected.issubset(codes), f"missing: {expected - codes}"


def test_offer_crud(s):
    # cleanup if exists
    s.delete(f"{API}/settings/offers/TEST20", timeout=30)
    # create
    r = s.post(f"{API}/settings/offers", json={
        "code":"TEST20","name":"Test","discount_type":"percentage","discount_value":20,"category":"Custom",
    }, timeout=30)
    assert r.status_code == 200
    codes = {o["code"] for o in r.json()["offers"]}
    assert "TEST20" in codes
    # update
    r2 = s.put(f"{API}/settings/offers/TEST20", json={
        "code":"TEST20","discount_value":25,"discount_type":"percentage",
    }, timeout=30)
    assert r2.status_code == 200
    test_offer = next(o for o in r2.json()["offers"] if o["code"]=="TEST20")
    assert test_offer["discount_value"] == 25
    # delete
    r3 = s.delete(f"{API}/settings/offers/TEST20", timeout=30)
    assert r3.status_code == 200
    codes = {o["code"] for o in r3.json()["offers"]}
    assert "TEST20" not in codes


def test_offer_empty_code_400(s):
    r = s.post(f"{API}/settings/offers", json={"code":"","name":"x","discount_value":5}, timeout=30)
    assert r.status_code == 400


# Stage 5 — Campaign content
def test_campaign_content_get_put(s):
    r = s.get(f"{API}/settings/campaign-content/ota_conversion_high", timeout=30)
    assert r.status_code == 200
    assert r.json()["key"] == "ota_conversion_high"
    assert r.json()["content"] is not None
    # PUT
    new_c = {"subject_lines":["A","B","C"],"sms":"hi","key_points":["x","y"],"tone":"warm","send_timing":"now"}
    r2 = s.put(f"{API}/settings/campaign-content/ota_conversion_high", json=new_c, timeout=30)
    assert r2.status_code == 200
    assert r2.json()["content"]["sms"] == "hi"
    # restore default-ish (just leave it)


def test_campaign_content_unknown_404(s):
    r = s.get(f"{API}/settings/campaign-content/nonexistent", timeout=30)
    assert r.status_code == 404


# Stage 1-4.5 regression
@pytest.mark.parametrize("path", [
    "/sources","/analytics/revenue","/scores/summary","/reports",
    "/settings/digest","/settings/commissions",
])
def test_previous_stages_still_ok(s, path):
    r = s.get(f"{API}{path}", timeout=30)
    assert r.status_code == 200, f"{path} -> {r.status_code}"
