from app.modules.admin_modules.models import AdminModule
from app.seed import seed_default_roles_and_permissions


def test_seed_admin_modules(db):
    seed_default_roles_and_permissions(db)
    db.commit()

    slugs = {module.slug for module in db.query(AdminModule).all()}

    assert "dashboard" in slugs
    assert "users" in slugs
    assert "bookings" in slugs
    assert "settings" in slugs


def test_list_admin_modules(client, admin_token, db):
    seed_default_roles_and_permissions(db)
    db.commit()

    response = client.get(
        "/api/modules/",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    slugs = {item["slug"] for item in response.json()["data"]}
    assert "dashboard" in slugs
    assert "permissions" in slugs
