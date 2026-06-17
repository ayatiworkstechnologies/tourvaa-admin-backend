def test_settings_section_endpoints(api_client):
    system = api_client.get("/settings/system")
    assert system["status"] == "success"
    assert "site_name" in system["data"]
    assert "maintenance_mode" in system["data"]

    payment = api_client.get("/settings/payment")
    assert payment["status"] == "success"
    assert isinstance(payment["data"], list)

    api_settings = api_client.get("/settings/api")
    assert api_settings["status"] == "success"
    assert isinstance(api_settings["data"], list)


def test_update_settings_sections(api_client, require_write_tests):
    system = api_client.put(
        "/settings/system",
        {
            "site_name": "Tourvaa",
            "company_name": "Tourvaa",
            "maintenance_mode": False,
        },
    )
    assert system["status"] == "success"
    assert system["data"]["site_name"] == "Tourvaa"

    payment = api_client.put(
        "/settings/payment",
        {
            "stripe_enabled": False,
            "paypal_enabled": False,
            "payment_surcharge_percentage": "0",
        },
    )
    assert payment["status"] == "success"
    assert payment["data"]["payment_surcharge_percentage"] == "0"

    api_settings = api_client.put(
        "/settings/api",
        {
            "google_maps_api_placeholder": "",
            "email_api_placeholder": "",
            "sms_api_placeholder": "",
            "brightlane_external_link_placeholder": "",
        },
    )
    assert api_settings["status"] == "success"
    assert "google_maps_api_placeholder" in api_settings["data"]
