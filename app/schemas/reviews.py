from typing import Optional
from pydantic import BaseModel, Field, field_validator


class ReviewCreate(BaseModel):
    booking_id: int
    rating: int = Field(ge=1, le=5)
    review_text: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("review_text")
    @classmethod
    def trim_text(cls, value: Optional[str]):
        return value.strip() if value else value


class ReviewModerate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str):
        value = value.strip().lower()
        if value not in {"approved", "rejected"}:
            raise ValueError("status must be 'approved' or 'rejected'")
        return value
