from pydantic import BaseModel
from typing import Optional


class PermissionCreate(BaseModel):
    name: str
    slug: str
    module: str
    action: str = "get"


class PermissionUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    module: Optional[str] = None
    action: Optional[str] = None
    is_active: Optional[bool] = None
