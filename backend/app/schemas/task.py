from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.microstep import MicroStepRead


class TaskCreate(BaseModel):
    title: str


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    created_at: datetime
    archived_at: datetime | None


class TaskDetail(TaskRead):
    microsteps: list[MicroStepRead]
