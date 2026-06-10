from typing import Optional

from pydantic import BaseModel


class EmailTemplateCreate(BaseModel):
    key: str
    name: str
    subject: str
    body: str
    is_active: bool = True


class EmailTemplateUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    is_active: Optional[bool] = None
