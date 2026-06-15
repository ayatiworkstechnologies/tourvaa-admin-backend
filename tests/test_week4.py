def test_dashboard_summary_requires_auth(client):
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 401


def test_dashboard_week4_endpoints(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}

    summary = client.get("/api/dashboard/summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["data"]["total_bookings"] == 0
    assert "pending_admin_users" in summary.json()["data"]

    bookings = client.get("/api/dashboard/bookings", headers=headers)
    assert bookings.status_code == 200
    assert "upcoming_bookings" in bookings.json()["data"]

    revenue = client.get("/api/dashboard/revenue", headers=headers)
    assert revenue.status_code == 200
    assert "monthly_revenue" in revenue.json()["data"]

    payments = client.get("/api/dashboard/payments", headers=headers)
    assert payments.status_code == 200
    assert "pending_payment_count" in payments.json()["data"]

    reports = client.get("/api/dashboard/reports", headers=headers)
    assert reports.status_code == 200
    assert reports.json()["data"]["total_reports"] == 6
    assert len(reports.json()["data"]["report_cards"]) > 0

    activities = client.get("/api/dashboard/recent-activities", headers=headers)
    assert activities.status_code == 200
    assert "recent_admin_actions" in activities.json()["data"]


def test_api_v1_dashboard_alias(client, admin_token):
    response = client.get(
        "/api/v1/dashboard/summary",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert "total_bookings" in response.json()["data"]


def test_settings_seed_week4_placeholders(client, admin_token):
    response = client.get(
        "/api/settings/",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    keys = {item["key"] for item in response.json()["data"]}

    assert "company_name" in keys
    assert "stripe_enabled" in keys
    assert "paypal_enabled" in keys
    assert "google_map_api_key" in keys
    assert "brightlane_external_link" in keys


def test_dedicated_payment_and_api_settings(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}

    payment = client.get("/api/settings/payment", headers=headers)
    assert payment.status_code == 200
    providers = {item["provider_name"] for item in payment.json()["data"]}
    assert {"stripe", "paypal"}.issubset(providers)

    payment_update = client.put(
        "/api/settings/payment/stripe",
        json={"is_enabled": True, "mode": "test"},
        headers=headers,
    )
    assert payment_update.status_code == 200
    assert payment_update.json()["data"]["is_enabled"] is True

    api_settings = client.get("/api/settings/api", headers=headers)
    assert api_settings.status_code == 200
    api_names = {item["api_name"] for item in api_settings.json()["data"]}
    assert "google_maps" in api_names

    api_update = client.put(
        "/api/settings/api/google_maps",
        json={"api_url": "https://maps.example.test", "is_enabled": True},
        headers=headers,
    )
    assert api_update.status_code == 200
    assert api_update.json()["data"]["is_enabled"] is True
