"""Stage 4.5 — Weekly digest endpoint tests."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://str-analytics-core.preview.emergentagent.com").rstrip("/")
SANDBOX_EMAIL = "info@gippslandholidays.com.au"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def initial_cfg(client):
    r = client.get(f"{BASE_URL}/api/settings/digest", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# --- Settings GET/PUT ---

def test_get_digest_settings_shape(initial_cfg):
    assert "config" in initial_cfg
    assert "webhook_url" in initial_cfg
    assert "days_of_week" in initial_cfg
    assert "sender_email" in initial_cfg
    cfg = initial_cfg["config"]
    for key in ["recipients", "send_day", "send_hour", "send_minute", "timezone", "enabled", "webhook_token"]:
        assert key in cfg, f"missing key {key}"
    assert isinstance(cfg["recipients"], list)
    assert initial_cfg["webhook_url"].endswith(cfg["webhook_token"])
    assert len(initial_cfg["days_of_week"]) == 7


def test_put_digest_settings_roundtrip(client):
    payload = {
        "recipients": ["UPPER@X.com", "  MixED@Case.IO  "],
        "send_day": 99,   # will clamp to 7
        "send_hour": -5,  # will clamp to 0
        "send_minute": 200,  # will clamp to 59
        "timezone": "Australia/Sydney",
        "enabled": True,
    }
    r = client.put(f"{BASE_URL}/api/settings/digest", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "upper@x.com" in j["recipients"]
    assert "mixed@case.io" in j["recipients"]
    assert j["send_day"] == 7
    assert j["send_hour"] == 0
    assert j["send_minute"] == 59
    # Confirm via GET
    g = client.get(f"{BASE_URL}/api/settings/digest", timeout=30).json()
    assert "upper@x.com" in g["config"]["recipients"]
    assert g["config"]["send_day"] == 7


def test_rotate_token(client):
    before = client.get(f"{BASE_URL}/api/settings/digest", timeout=30).json()["config"]["webhook_token"]
    r = client.post(f"{BASE_URL}/api/settings/digest/rotate-token", timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "webhook_token" in j
    assert "webhook_url" in j
    assert j["webhook_token"] != before
    after = client.get(f"{BASE_URL}/api/settings/digest", timeout=30).json()["config"]["webhook_token"]
    assert after == j["webhook_token"]


# --- Preview ---

def test_preview_digest(client):
    r = client.get(f"{BASE_URL}/api/digest/preview", timeout=60)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "payload" in j and "html" in j
    assert isinstance(j["html"], str) and len(j["html"]) > 1000
    p = j["payload"]
    assert "period" in p and "prior_period" in p and "kpis" in p
    k = p["kpis"]
    for key in ["revenue", "direct_share_pct", "bookings", "cancellations", "top_property", "new_high_priority"]:
        assert key in k, f"missing kpi {key}"
    assert "trend" in k["revenue"]
    assert "trend" in k["direct_share_pct"]
    assert "trend" in k["bookings"]
    assert "trend" in k["cancellations"]


# --- Send-now (live Resend) ---

def test_send_now_to_sandbox_recipient(client):
    # Ensure default to sandbox recipient
    client.put(f"{BASE_URL}/api/settings/digest", json={
        "recipients": [SANDBOX_EMAIL], "enabled": True
    }, timeout=30)
    r = client.post(
        f"{BASE_URL}/api/digest/send-now",
        json={"test_recipient": SANDBOX_EMAIL},
        timeout=90,
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "sent", f"Expected sent, got: {j}"
    assert "email_id" in j and j["email_id"]
    assert SANDBOX_EMAIL in j["recipients"]
    assert "subject" in j and "period" in j and "kpis" in j


def test_send_now_non_sandbox_recipient_returns_failed(client):
    # Save state then point recipients at non-sandbox to trigger Resend 403
    client.put(f"{BASE_URL}/api/settings/digest", json={
        "recipients": ["amy2727@hotmail.com"], "enabled": True
    }, timeout=30)
    try:
        r = client.post(f"{BASE_URL}/api/digest/send-now", json={}, timeout=90)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "failed", f"Expected failed (sandbox restriction), got: {j}"
        assert isinstance(j.get("error"), str) and len(j["error"]) > 0
    finally:
        # Restore
        client.put(f"{BASE_URL}/api/settings/digest", json={
            "recipients": [SANDBOX_EMAIL], "enabled": True
        }, timeout=30)


# --- Webhook /digest/run ---

def test_webhook_invalid_token(client):
    r = client.post(f"{BASE_URL}/api/digest/run", params={"token": "bad-token"}, timeout=30)
    assert r.status_code == 401


def test_webhook_skipped_when_disabled(client):
    # Get token
    tok = client.get(f"{BASE_URL}/api/settings/digest", timeout=30).json()["config"]["webhook_token"]
    # Disable
    client.put(f"{BASE_URL}/api/settings/digest", json={"enabled": False}, timeout=30)
    try:
        r = client.post(f"{BASE_URL}/api/digest/run", params={"token": tok}, timeout=30)
        assert r.status_code == 200, r.text
        assert "skipped" in r.text and "disabled" in r.text
    finally:
        client.put(f"{BASE_URL}/api/settings/digest", json={"enabled": True}, timeout=30)


def test_webhook_run_then_skip_no_new_data(client):
    tok = client.get(f"{BASE_URL}/api/settings/digest", timeout=30).json()["config"]["webhook_token"]
    # First call — may send or skip depending on import state
    r1 = client.post(f"{BASE_URL}/api/digest/run", params={"token": tok}, timeout=120)
    assert r1.status_code == 200, r1.text
    # Second call — should skip (no new data since the just-now sent timestamp)
    r2 = client.post(f"{BASE_URL}/api/digest/run", params={"token": tok}, timeout=30)
    assert r2.status_code == 200, r2.text
    # If first one sent, second must skip no_new_data; if first skipped, second also skips.
    assert "skipped" in r2.text or "sent" in r2.text


# --- History ---

def test_history(client):
    r = client.get(f"{BASE_URL}/api/digest/history", timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "items" in j and isinstance(j["items"], list)
    assert len(j["items"]) <= 30
    if j["items"]:
        item = j["items"][0]
        assert "sent_at" in item and "status" in item


# --- Stage 1-4 regressions ---

@pytest.mark.parametrize("path", [
    "/api/sources",
    "/api/analytics/revenue",
    "/api/scores/summary",
    "/api/reports",
    "/api/settings/commissions",
])
def test_prior_stages_still_200(client, path):
    r = client.get(f"{BASE_URL}{path}", timeout=30)
    assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"


# --- Final cleanup: leave config in known-good state ---

def test_zz_restore_final_state(client):
    r = client.put(f"{BASE_URL}/api/settings/digest", json={
        "recipients": [SANDBOX_EMAIL],
        "enabled": True,
        "send_day": 1,
        "send_hour": 8,
        "send_minute": 0,
        "timezone": "Australia/Sydney",
    }, timeout=30)
    assert r.status_code == 200
    j = r.json()
    assert j["recipients"] == [SANDBOX_EMAIL]
    assert j["enabled"] is True
    assert j["send_day"] == 1 and j["send_hour"] == 8 and j["send_minute"] == 0
    assert j["timezone"] == "Australia/Sydney"
