import requests
from conftest import BASE_URL


def test_notifications_reports_sessions_activity(headers):
    for path in ["/notifications", "/reports/summary", "/activity-logs", "/sessions"]:
        resp = requests.get(f"{BASE_URL}{path}", headers=headers, timeout=10)
        assert resp.status_code == 200, f"{path}: {resp.text}"
