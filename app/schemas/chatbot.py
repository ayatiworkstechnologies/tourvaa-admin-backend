from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_key: Optional[str] = None


class ChatMessageResponse(BaseModel):
    reply: str
    session_key: str
    action_type: Optional[str] = None
    action_data: Optional[dict] = None


class FAQBase(BaseModel):
    question: str
    answer: str
    category: str = "general"
    sort_order: int = 0
    is_active: bool = True


class FAQCreate(FAQBase):
    pass


class FAQUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    category: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class FAQResponse(FAQBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
