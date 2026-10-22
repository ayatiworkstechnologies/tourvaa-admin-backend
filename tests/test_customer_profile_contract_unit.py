import pytest
from pydantic import ValidationError

from app.schemas.auth import ChangeRegistrationEmailSchema
from app.schemas.customers import CustomerProfileUpdate


def test_customer_profile_accepts_blank_optional_emergency_email():
    payload = CustomerProfileUpdate(emergency_email="   ")

    assert payload.emergency_email is None


def test_customer_profile_rejects_legacy_aliases():
    with pytest.raises(ValidationError, match="extra_forbidden"):
        CustomerProfileUpdate(passport_no="legacy-value")


def test_change_registration_email_accepts_selected_country_id():
    payload = ChangeRegistrationEmailSchema(
        change_token="token",
        email="traveller@tourvaa.co.in",
        country_id=91,
    )

    assert payload.country_id == 91
