from conftest import data_id, unique


def test_supplier_write_actions(api_client, require_write_tests):
    supplier_id = data_id(
        api_client.post(
            "/suppliers/",
            {
                "supplier_name": unique("Pytest Supplier"),
                "supplier_type": "local",
                "years_in_operation": 1,
                "status": "inactive",
                "approval_status": "pending",
            },
        )
    )

    assert api_client.get(f"/suppliers/{supplier_id}")["data"]["id"] == supplier_id
    api_client.put(f"/suppliers/{supplier_id}", {"admin_comments": "Checked by pytest"})
    api_client.patch(
        f"/suppliers/{supplier_id}/markup",
        {"markup_type": "percentage", "markup_value": 5},
    )
    api_client.patch(
        f"/suppliers/{supplier_id}/partial-approve",
        {"reason": "Pytest check"},
    )


def test_agent_write_actions(api_client, require_write_tests):
    agent_id = data_id(
        api_client.post(
            "/agents/",
            {
                "agent_name": unique("Pytest Agent"),
                "agent_type": "agency",
                "years_in_operation": 1,
                "status": "inactive",
                "approval_status": "pending",
            },
        )
    )

    assert api_client.get(f"/agents/{agent_id}")["data"]["id"] == agent_id
    api_client.put(f"/agents/{agent_id}", {"admin_comments": "Checked by pytest"})
    api_client.patch(
        f"/agents/{agent_id}/discount",
        {"discount_type": "percentage", "discount_value": 5},
    )
    api_client.patch(
        f"/agents/{agent_id}/partial-approve",
        {"reason": "Pytest check"},
    )


def test_affiliate_write_actions(api_client, require_write_tests):
    affiliate_id = data_id(
        api_client.post(
            "/affiliates/",
            {
                "business_type": "publisher",
                "name": unique("Pytest Affiliate"),
                "email": f"pytest-affiliate-{unique('').strip().replace(' ', '-')}@example.com",
                "phone": "",
                "website_url": "https://example.com",
                "status": "inactive",
                "approval_status": "pending",
            },
        )
    )

    assert api_client.get(f"/affiliates/{affiliate_id}")["data"]["id"] == affiliate_id
    api_client.patch(
        f"/affiliates/{affiliate_id}/api-link",
        {"api_link": "https://api.example.com/affiliate"},
    )
    api_client.patch(f"/affiliates/{affiliate_id}/approve")


def test_cms_write_actions(api_client, require_write_tests):
    country_id = data_id(
        api_client.post(
            "/countries",
            {
                "country_name": unique("Pytest Country"),
                "country_code": f"T{unique('').strip()[-6:]}",
                "phone_code": "+91",
                "currency_code": "INR",
                "status": "active",
            },
        )
    )
    city_id = data_id(
        api_client.post(
            "/cities",
            {
                "country_id": country_id,
                "city_name": unique("Pytest City"),
                "status": "active",
            },
        )
    )
    category_id = data_id(
        api_client.post(
            "/tour-categories",
            {
                "category_name": unique("Pytest Category"),
                "slug": "",
                "description": "Created by pytest",
                "image": "",
                "status": "active",
            },
        )
    )
    subcategory_id = data_id(
        api_client.post(
            "/tour-subcategories",
            {
                "category_id": category_id,
                "subcategory_name": unique("Pytest Subcategory"),
                "slug": "",
                "description": "Created by pytest",
                "image": "",
                "status": "active",
            },
        )
    )
    tour_id = data_id(
        api_client.post(
            "/tours",
            {
                "title": unique("Pytest Tour"),
                "slug": "",
                "subtitle": "",
                "price_start_per_person": 100,
                "currency": "USD",
                "country_id": country_id,
                "city_id": city_id,
                "category_id": category_id,
                "subcategory_ids": [subcategory_id],
                "start_location": "",
                "finish_location": "",
                "number_of_days": 1,
                "short_description": "Created by pytest",
                "long_description": "",
                "status": "draft",
            },
        )
    )

    api_client.patch(f"/countries/{country_id}/status", {"status": "inactive"})
    api_client.patch(f"/cities/{city_id}/status", {"status": "inactive"})
    api_client.patch(f"/tour-categories/{category_id}/status", {"status": "inactive"})
    api_client.patch(f"/tour-subcategories/{subcategory_id}/status", {"status": "inactive"})
    api_client.patch(f"/tours/{tour_id}/status", {"status": "published"})
