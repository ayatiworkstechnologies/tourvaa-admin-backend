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
