def test_customer_read_endpoints(api_client):
    list_payload = api_client.get("/customers")
    assert list_payload["status"] == "success"
    assert isinstance(list_payload["data"], list)

    customers = list_payload["data"]
    if not customers:
        return

    customer_id = customers[0]["id"]
    detail = api_client.get(f"/customers/{customer_id}")
    assert detail["status"] == "success"
    assert detail["data"]["id"] == customer_id

    for suffix in ["bookings", "payments", "communications"]:
        payload = api_client.get(f"/customers/{customer_id}/{suffix}")
        assert payload["status"] == "success"
        assert "items" in payload
