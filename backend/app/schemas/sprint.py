from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SprintStartRequest(BaseModel):
    task_id: UUID | None = None
    duration_minutes: int


class SprintFinishRequest(BaseModel):
    status: str


class SprintEventCreate(BaseModel):
    type: str
    payload: dict = Field(default_factory=dict)


class SprintReflectionCreate(BaseModel):
    outcome: str
    reason: str | None = None
    next_step: str | None = None


class SprintRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID | None
    duration_minutes: int
    started_at: datetime
    ended_at: datetime | None
    status: str


class SprintEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    payload: dict
    created_at: datetime


class SprintReflectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    outcome: str
    next_step: str | None


class TodayHistorySprint(BaseModel):
    id: UUID
    task_id: UUID | None
    duration_minutes: int
    status: str
    started_at: datetime
    ended_at: datetime | None
    reflection: SprintReflectionRead | None = None


class TodayHistoryResponse(BaseModel):
    date: str
    sprints: list[TodayHistorySprint]


class StatsSummaryResponse(BaseModel):
    days: int
    total_sprints: int
    total_minutes: int
    current_streak_days: int
