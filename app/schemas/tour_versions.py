from pydantic import BaseModel, Field, field_validator
from typing import Optional

SEVERITIES = {"info", "minor", "required", "critical"}


class ReviewCommentCreate(BaseModel):
    section: str = Field(min_length=1, max_length=50)
    field_name: Optional[str] = Field(default=None, max_length=100)
    comment: str = Field(min_length=1)
    severity: str = Field(default="minor", max_length=20)

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str):
        if v not in SEVERITIES:
            raise ValueError(f"severity must be one of {SEVERITIES}")
        return v


class TourVersionReject(BaseModel):
    rejection_reason: str
    # Section/field-level feedback attached to this rejection, shown to the
    # supplier inside the matching editor step -- optional so existing
    # callers that only send a rejection_reason keep working unchanged.
    comments: list[ReviewCommentCreate] = Field(default_factory=list)
