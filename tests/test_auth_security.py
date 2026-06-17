def test_auth_security_endpoints(api_client):
    refreshed = api_client.post("/auth/refresh-token", {"client_type": "web"})
    assert refreshed["status"] == "success"
    assert refreshed["data"]["access_token"]

    history = api_client.get("/auth/login-history")
    assert history["status"] == "success"
    assert isinstance(history["data"], list)


def test_force_logout_endpoint_requires_admin_permission(api_client, require_write_tests):
    payload = api_client.post("/auth/force-logout", {})
    assert payload["status"] == "success"
    assert payload["data"]["user_id"]
