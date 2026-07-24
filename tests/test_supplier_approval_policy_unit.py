from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.auth.permissions import ensure_approved_supplier
from app.models.suppliers import Supplier


def supplier_user(**overrides):
    values = {
        "id": 10,
        "user_type": "SUPPLIER",
        "role": SimpleNamespace(slug="supplier"),
        "email_verified": True,
        "email_verified_at": object(),
        "account_status": "ACTIVE",
        "is_active": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def database_with_supplier(status: str):
    db = MagicMock()
    profile = SimpleNamespace(id=20, user_id=10, approval_status=status)
    db.query.return_value.filter.return_value.first.return_value = profile
    return db, profile


def test_pending_supplier_receives_consistent_approval_error():
    db, _ = database_with_supplier("PENDING")

    with pytest.raises(HTTPException) as raised:
        ensure_approved_supplier(db, supplier_user())

    assert raised.value.status_code == 403
    assert raised.value.detail["code"] == "SUPPLIER_APPROVAL_REQUIRED"
    assert raised.value.detail["success"] is False


def test_approved_supplier_is_returned():
    db, profile = database_with_supplier("APPROVED")
    assert ensure_approved_supplier(db, supplier_user()) is profile


@pytest.mark.parametrize(
    "changes",
    [
        {"email_verified": False},
        {"email_verified_at": None},
        {"account_status": "SUSPENDED", "is_active": False},
    ],
)
def test_supplier_must_also_be_verified_and_active(changes):
    db, _ = database_with_supplier("APPROVED")
    with pytest.raises(HTTPException) as raised:
        ensure_approved_supplier(db, supplier_user(**changes))
    assert raised.value.status_code == 403
