from conftest import unique, data_id


def test_customer_write_and_action_flow(api_client, require_write_tests):
    email = f"customer{unique('').strip().replace(' ', '').lower()}@example.com"
    api_client.post(
        "/auth/register",
        {
            "name": unique("Customer User"),
            "email": email,
            "phone": "+919876543210",
            "password": "Customer@123",
        },
    )

    customer = api_client.post(
        "/customers/",
        {
            "full_name": unique("Customer"),
            "email": email,
            "phone": "+919876543210",
            "country": "India",
            "city": "Chennai",
            "status": "active",
        },
    )
    customer_id = data_id(customer)

    status = api_client.patch(f"/customers/{customer_id}/status", {"status": "inactive"})
    assert status["status"] == "success"
    assert status["data"]["status"] == "inactive"

    blocked = api_client.patch(f"/customers/{customer_id}/block", {"reason": "Test block"})
    assert blocked["status"] == "success"
    assert blocked["data"]["is_blocked"] is True

    unblocked = api_client.patch(f"/customers/{customer_id}/unblock")
    assert unblocked["status"] == "success"
    assert unblocked["data"]["is_blocked"] is False

    reset = api_client.post(f"/customers/{customer_id}/reset-password")
    assert reset["status"] == "success"

    message = api_client.post(
        f"/customers/{customer_id}/communications",
        {
            "subject": "Test message",
            "message": "This is an automated test message.",
            "message_type": "admin_message",
        },
    )
    assert message["status"] == "success"
