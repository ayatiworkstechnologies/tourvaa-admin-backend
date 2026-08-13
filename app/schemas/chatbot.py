from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_key: Optional[str] = None
    page_url: Optional[str] = Field(default=None, max_length=500)


class ChatMessageResponse(BaseModel):
    reply: str
    session_key: str
    action_type: Optional[str] = None
    action_data: Optional[dict] = None


class ChatFeedbackCreate(BaseModel):
    message_id: int
    rating: int
    comment: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("rating")
    @classmethod
    def rating_must_be_thumb(cls, v: int) -> int:
        if v not in (1, -1):
            raise ValueError("rating must be 1 (up) or -1 (down)")
        return v


class ChatFeedbackResponse(BaseModel):
    id: int
    message_id: int
    rating: int
    comment: Optional[str] = None

    class Config:
        from_attributes = True


class FAQBase(BaseModel):
    question: str
    answer: str
    category: str = "general"
    sort_order: int = 0
    is_active: bool = True
    is_public: bool = True


class FAQCreate(FAQBase):
    pass


class FAQUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    category: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    is_public: Optional[bool] = None


class FAQResponse(FAQBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
