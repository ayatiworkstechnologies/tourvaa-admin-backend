from typing import Optional
from pydantic import BaseModel

class NotificationCreate(BaseModel):
    user_id: Optional[int] = None
    notification_type: str
    title: str
    message: str
    channel: str = "in_app"
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    metadata: dict | None = None
