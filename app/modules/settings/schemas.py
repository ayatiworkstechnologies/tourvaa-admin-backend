from pydantic import BaseModel
from typing import Optional


class SettingUpdate(BaseModel):
    value: Optional[str] = None


class SettingsBulkUpdate(BaseModel):
    settings: dict[str, str | None]
