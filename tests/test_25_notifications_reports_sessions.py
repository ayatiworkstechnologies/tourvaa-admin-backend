import requests

from tests.conftest import BASE_URL, skip_if_readonly


def test_notifications_reports_sessions_activity(headers):
    for path in ["/notifications", "/reports/summary", "/activity-logs", "/sessions"]:
        resp = requests.get(f"{BASE_URL}{path}", headers=headers, timeout=10)
        assert resp.status_code == 200, f"{path}: {resp.text}"


def test_audit_logs_alias_and_export(headers):
    resp = requests.get(f"{BASE_URL}/audit-logs", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text

    export = requests.get(f"{BASE_URL}/audit-logs/export", headers=headers, timeout=10)
    assert export.status_code == 200, export.text


def test_reports_snapshot(headers):
    resp = requests.get(f"{BASE_URL}/reports/snapshot", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_notification_read_and_retry_not_found(headers):
    read = requests.patch(f"{BASE_URL}/notifications/999999999/read", headers=headers, timeout=10)
    assert read.status_code == 404, read.text

    retry = requests.post(f"{BASE_URL}/notifications/999999999/retry", headers=headers, timeout=10)
    assert retry.status_code == 404, retry.text


@skip_if_readonly()
def test_notification_mark_all_read(headers):
    me = requests.get(f"{BASE_URL}/auth/me", headers=headers, timeout=10)
    user_id = me.json()["data"]["user"]["id"]
    resp = requests.patch(f"{BASE_URL}/notifications/mark-all-read", params={"user_id": user_id}, headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    assert "updated" in resp.json()["data"]


@skip_if_readonly()
def test_notification_push_subscribe_and_unsubscribe(headers):
    payload = {"endpoint": "https://example.com/push/pytest-endpoint", "p256dh": "test-p256dh-key", "auth": "test-auth-key"}
    sub = requests.post(f"{BASE_URL}/notifications/push/subscribe", json=payload, headers=headers, timeout=10)
    assert sub.status_code == 200, sub.text

    unsub = requests.delete(f"{BASE_URL}/notifications/push/subscribe", json=payload, headers=headers, timeout=10)
    assert unsub.status_code == 200, unsub.text


@skip_if_readonly()
def test_notification_push_broadcast(headers):
    resp = requests.post(f"{BASE_URL}/notifications/push/broadcast", json={
        "title": "Pytest broadcast", "body": "Automated test notification",
    }, headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_session_revoke_and_force_logout_not_found(headers):
    revoke = requests.post(f"{BASE_URL}/sessions/999999999/revoke", headers=headers, timeout=10)
    assert revoke.status_code in (200, 404), revoke.text

    force_logout = requests.post(f"{BASE_URL}/sessions/users/999999999/force-logout", headers=headers, timeout=10)
    assert force_logout.status_code in (200, 404), force_logout.text


@skip_if_readonly()
def test_session_expire_inactive(headers):
    resp = requests.post(f"{BASE_URL}/sessions/expire-inactive", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
