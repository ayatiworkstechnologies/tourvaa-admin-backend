from pydantic import BaseModel, ConfigDict, Field, field_validator
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
    # A message id alone is enumerable. Requiring the opaque chat-session key
    # makes sure a visitor can rate only replies in their own conversation.
    session_key: str = Field(min_length=32, max_length=64)
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

    model_config = ConfigDict(from_attributes=True)


class FAQBase(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1)
    category: str = "general"
    sort_order: int = 0
    is_active: bool = True
    is_public: bool = True

    @field_validator("question", "answer")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class FAQCreate(FAQBase):
    pass


class FAQUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    category: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    is_public: Optional[bool] = None

    @field_validator("question", "answer")
    @classmethod
    def updated_text_must_not_be_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class FAQResponse(FAQBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
