def test_core_authenticated_endpoints(api_client):
    assert api_client.get("/health")["status"] == "success"
    assert api_client.get("/auth/me")["status"] == "success"
    assert api_client.get("/dashboard/me")["status"] == "success"


def test_rbac_endpoints(api_client):
    assert api_client.get("/permissions/")["status"] == "success"
    assert api_client.get("/roles/")["status"] == "success"
    assert api_client.get("/modules")["status"] == "success"
    assert api_client.get("/modules/")["status"] == "success"
