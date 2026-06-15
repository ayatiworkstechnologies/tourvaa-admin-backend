from pydantic import BaseModel


class AdminModuleResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: str
    is_active: bool
    is_system: bool

    class Config:
        from_attributes = True
