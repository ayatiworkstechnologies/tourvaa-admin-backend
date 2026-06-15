from app.modules.audit.models import AuditLog
from app.modules.users.models import User
from app.security import hash_password


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def customer_payload(email="traveler@example.com"):
    return {
        "full_name": "Traveler One",
        "email": email,
        "phone": "+919876543210",
        "country": "India",
        "state": "Tamil Nadu",
        "city": "Chennai",
        "pincode": "600001",
        "status": "active",
    }


def create_customer(client, admin_token, email="traveler@example.com"):
    response = client.post(
        "/api/customers/",
        json=customer_payload(email),
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200
    return response.json()["data"]


def test_customer_list_and_detail_api(client, admin_token):
    customer = create_customer(client, admin_token)

    list_response = client.get(
        "/api/customers/?page=1&limit=10&search=traveler",
        headers=auth_headers(admin_token),
    )
    assert list_response.status_code == 200
    body = list_response.json()
    assert body["total"] == 1
    assert body["items"][0]["email"] == "traveler@example.com"

    detail_response = client.get(
        f"/api/customers/{customer['id']}",
        headers=auth_headers(admin_token),
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["full_name"] == "Traveler One"


def test_customer_status_block_and_unblock(client, admin_token):
    customer = create_customer(client, admin_token, "status@example.com")

    inactive_response = client.patch(
        f"/api/customers/{customer['id']}/status",
        json={"status": "inactive"},
        headers=auth_headers(admin_token),
    )
    assert inactive_response.status_code == 200
    assert inactive_response.json()["data"]["status"] == "inactive"

    block_response = client.post(
        f"/api/customers/{customer['id']}/block",
        headers=auth_headers(admin_token),
    )
    assert block_response.status_code == 200
    assert block_response.json()["data"]["is_blocked"] is True

    unblock_response = client.post(
        f"/api/customers/{customer['id']}/unblock",
        headers=auth_headers(admin_token),
    )
    assert unblock_response.status_code == 200
    assert unblock_response.json()["data"]["status"] == "active"


def test_block_requires_reason_and_blocks_linked_user(client, db, admin_token):
    email = "blocked-customer@example.com"
    user = User(
        name="Blocked Customer",
        email=email,
        phone="",
        profile_image="",
        address="",
        country="",
        state="",
        city="",
        pincode="",
        password=hash_password("Password@123"),
        role_id=None,
        is_active=True,
        approval_status="approved",
    )
    db.add(user)
    db.commit()

    customer = create_customer(client, admin_token, email)

    missing_reason = client.patch(
        f"/api/customers/{customer['id']}/block",
        json={"reason": ""},
        headers=auth_headers(admin_token),
    )
    assert missing_reason.status_code == 422

    block_response = client.patch(
        f"/api/customers/{customer['id']}/block",
        json={"reason": "Suspicious booking activity"},
        headers=auth_headers(admin_token),
    )
    assert block_response.status_code == 200
    assert block_response.json()["data"]["blocked_reason"] == "Suspicious booking activity"

    db.refresh(user)
    assert user.is_active is False

    unblock_response = client.patch(
        f"/api/customers/{customer['id']}/unblock",
        headers=auth_headers(admin_token),
    )
    assert unblock_response.status_code == 200
    db.refresh(user)
    assert user.is_active is True


def test_customer_histories(client, admin_token):
    customer = create_customer(client, admin_token, "history@example.com")

    for suffix in ["bookings", "payments", "communications"]:
        response = client.get(
            f"/api/customers/{customer['id']}/{suffix}",
            headers=auth_headers(admin_token),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["data"]
        assert body["items"]
        assert body["total"] >= 1


def test_reset_customer_password_sets_token(client, db, admin_token, monkeypatch):
    monkeypatch.setattr("app.modules.customers.service.send_email", lambda *args, **kwargs: None)
    email = "login-customer@example.com"
    user = User(
        name="Login Customer",
        email=email,
        phone="",
        profile_image="",
        address="",
        country="",
        state="",
        city="",
        pincode="",
        password=hash_password("Password@123"),
        role_id=None,
        is_active=True,
        approval_status="approved",
    )
    db.add(user)
    db.commit()

    customer = create_customer(client, admin_token, email)
    response = client.post(
        f"/api/customers/{customer['id']}/reset-password",
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 200
    db.refresh(user)
    assert user.reset_password_token
    assert user.reset_password_expires_at


def test_send_customer_message_stores_communication_and_audit(client, db, admin_token, monkeypatch):
    monkeypatch.setattr("app.modules.customers.service.send_email", lambda *args, **kwargs: None)
    customer = create_customer(client, admin_token, "message@example.com")

    response = client.post(
        f"/api/customers/{customer['id']}/communications",
        json={
            "subject": "Travel update",
            "message": "Your travel update is ready.",
            "booking_id": 1,
        },
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["subject"] == "Travel update"
    assert body["email_status"] == "sent"

    history = client.get(
        f"/api/customers/{customer['id']}/communications",
        headers=auth_headers(admin_token),
    )
    assert history.status_code == 200
    assert history.json()["items"][0]["subject"] == "Travel update"

    audit = (
        db.query(AuditLog)
        .filter(AuditLog.action == "send_customer_message")
        .first()
    )
    assert audit is not None
