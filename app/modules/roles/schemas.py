from pydantic import BaseModel
from typing import Optional, List


class RoleCreate(BaseModel):
    name: str
    slug: str


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    is_active: Optional[bool] = None


class AssignPermissions(BaseModel):
    permission_ids: List[int]