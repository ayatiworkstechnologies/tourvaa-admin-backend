def test_dashboard_analytics_endpoints(api_client):
    endpoints = [
        "/dashboard/summary?start_date=2026-06-01&end_date=2026-06-16",
        "/dashboard/bookings?country_id=1",
        "/dashboard/revenue",
        "/dashboard/payments",
        "/dashboard/recent-activities",
    ]

    for endpoint in endpoints:
        payload = api_client.get(endpoint)
        assert payload["status"] == "success"
        assert "data" in payload


def test_dashboard_summary_includes_required_cards(api_client):
    payload = api_client.get("/dashboard/summary")
    data = payload["data"]

    for key in [
        "total_bookings",
        "total_customers",
        "total_suppliers",
        "total_agents",
        "total_revenue",
        "pending_payments",
        "upcoming_bookings",
        "pending_suppliers",
        "pending_agents",
    ]:
        assert key in data
