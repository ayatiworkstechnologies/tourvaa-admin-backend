from pydantic import BaseModel
from typing import Optional


class TourVersionReject(BaseModel):
    rejection_reason: str
