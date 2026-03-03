from typing import Any

from pydantic import BaseModel, Field


class FeedbackCreate(BaseModel):
    message: str = Field(min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)


class FeedbackRead(BaseModel):
    id: str
    message: str
    context: dict[str, Any]
    created_at: str
