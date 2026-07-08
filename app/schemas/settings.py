from pydantic import BaseModel
from typing import Optional


class SettingUpdate(BaseModel):
    value: Optional[str] = None


class SettingsBulkUpdate(BaseModel):
    settings: dict[str, str | None]


class PaymentSettingUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    public_key: Optional[str] = None
    secret_key: Optional[str] = None
    surcharge_percentage: Optional[str] = None
    mode: Optional[str] = None


class ApiSettingUpdate(BaseModel):
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    api_url: Optional[str] = None
    is_enabled: Optional[bool] = None


class SystemSettingsUpdate(BaseModel):
    site_name: Optional[str] = None
    company_name: Optional[str] = None
    support_email: Optional[str] = None
    support_phone: Optional[str] = None
    default_country: Optional[str] = None
    default_currency: Optional[str] = None
    timezone: Optional[str] = None
    logo: Optional[str] = None
    favicon: Optional[str] = None
    maintenance_mode: Optional[bool | str] = None


class PaymentSettingsUpdate(BaseModel):
    stripe_enabled: Optional[bool] = None
    stripe_public_key: Optional[str] = None
    stripe_secret_key: Optional[str] = None
    stripe_secret_placeholder: Optional[str] = None
    paypal_enabled: Optional[bool] = None
    paypal_client_id: Optional[str] = None
    paypal_client_id_placeholder: Optional[str] = None
    paypal_secret: Optional[str] = None
    paypal_secret_placeholder: Optional[str] = None
    payment_surcharge_percentage: Optional[str] = None
    default_payment_mode: Optional[str] = None


class ApiSettingsUpdate(BaseModel):
    google_map_api_key: Optional[str] = None
    google_maps_api_placeholder: Optional[str] = None
    email_api_key: Optional[str] = None
    email_api_placeholder: Optional[str] = None
    sms_api_key: Optional[str] = None
    sms_api_placeholder: Optional[str] = None
    brightlane_external_link: Optional[str] = None
    brightlane_external_link_placeholder: Optional[str] = None
