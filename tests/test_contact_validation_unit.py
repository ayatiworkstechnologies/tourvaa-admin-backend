"""Regression coverage for public and portal contact-value validation."""

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.routers.public import ContactMessageRequest
from app.schemas.affiliates import AffiliateInvoicingUpdate
from app.schemas.agents import AgentContactUpdate
from app.schemas.customers import SavedTravellerRequest
from app.schemas.suppliers import SupplierContactUpdate
from app.schemas.auth import UnifiedRegisterSchema
from app.services import auth
from app.models.cms import Country


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ContactMessageRequest(name="A", email="a@example.com", subject="Help", message="Please help", phone="not-a-phone"),
        lambda: AgentContactUpdate(email="not-an-email", phone="not-a-phone"),
        lambda: SupplierContactUpdate(email="not-an-email", phone="not-a-phone"),
        lambda: AffiliateInvoicingUpdate(email="not-an-email", phone="not-a-phone"),
        lambda: SavedTravellerRequest(traveller_name="A", email="not-an-email", phone="not-a-phone"),
    ],
)
def test_contact_payloads_reject_invalid_email_or_phone(factory):
    with pytest.raises(ValidationError):
        factory()


def test_contact_payloads_accept_normalized_e164_details():
    contact = ContactMessageRequest(
        name="Alex", email="alex@example.com", subject="Help", message="Please help", phone="+919876543210"
    )
    traveller = SavedTravellerRequest(traveller_name="Alex", email="Alex@Example.COM", phone="+919876543210")

    assert contact.phone == "+919876543210"
    assert traveller.email == "alex@example.com"


@pytest.mark.parametrize("mobile_number", ["6789", "678901", "1234567890"])
def test_indian_registration_rejects_invalid_mobile_numbers(mobile_number):
    with pytest.raises(ValidationError, match="valid mobile number"):
        UnifiedRegisterSchema(
            account_type="CUSTOMER", first_name="Alex", email="alex@ayatiworks.com",
            country_id=1, country_iso="IN", country_code="+91",
            mobile_number=mobile_number, accepted_terms=True,
        )


def test_indian_registration_accepts_valid_mobile_number():
    data = UnifiedRegisterSchema(
        account_type="CUSTOMER", first_name="Alex", email="alex@ayatiworks.com",
        country_id=1, country_iso="IN", country_code="+91",
        mobile_number="6789012345", accepted_terms=True,
    )

    assert data.mobile_number == "6789012345"


@pytest.mark.parametrize(
    "email",
    ["xyz@gmail.com", "test@example.com", "dummy@mailinator.com", "user+name@test.com"],
)
def test_registration_rejects_placeholder_or_disposable_email(email):
    with pytest.raises(ValidationError, match="real email address"):
        UnifiedRegisterSchema(
            account_type="CUSTOMER", first_name="Alex", email=email,
            country_id=1, country_iso="IN", country_code="+91",
            mobile_number="6789012345", accepted_terms=True,
        )


def test_registration_accepts_non_placeholder_email():
    data = UnifiedRegisterSchema(
        account_type="CUSTOMER", first_name="Alex", email="alex.smith@gmail.com",
        country_id=1, country_iso="IN", country_code="+91",
        mobile_number="6789012345", accepted_terms=True,
    )

    assert str(data.email) == "alex.smith@gmail.com"


def test_registration_rejects_calling_code_that_conflicts_with_catalogue_country():
    with pytest.raises(ValidationError, match="valid mobile number"):
        UnifiedRegisterSchema(
            account_type="CUSTOMER", first_name="Alex", email="alex@ayatiworks.com",
            country_id=1, country_iso="IN", country_code="+61", mobile_number="9876543210", accepted_terms=True,
        )


def test_registration_accepts_equivalent_catalogue_calling_code_formats():
    data = UnifiedRegisterSchema(
        account_type="CUSTOMER", first_name="Alex", email="alex@ayatiworks.com",
        country_id=1, country_iso="IN", country_code="+91", mobile_number="9876543210", accepted_terms=True,
    )
    country = SimpleNamespace(id=1, country_name="India", country_code="IN", phone_code="91.0")
    db = MagicMock()

    def query(model):
        result = MagicMock()
        result.filter.return_value.first.return_value = country if model is Country else None
        return result

    db.query.side_effect = query
    with pytest.raises(HTTPException) as exc:
        auth.register_unified_user(db, data)

    # The registration now passes country-code validation and reaches the
    # expected missing-role guard in this isolated test fixture.
    assert exc.value.status_code == 400
    assert exc.value.detail == "Selected account type is not available"
