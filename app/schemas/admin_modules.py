from pydantic import BaseModel, ConfigDict


class AdminModuleResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: str
    is_active: bool
    is_system: bool

    model_config = ConfigDict(from_attributes=True)
