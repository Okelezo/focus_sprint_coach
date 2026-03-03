from uuid import UUID

from pydantic import BaseModel


class AIBreakdownRequest(BaseModel):
    task_id: UUID | None = None
    task_title: str | None = None
    context: str | None = None


class AIBreakdownResponse(BaseModel):
    task_id: UUID | None = None
    microsteps: list[str]


class AIBlockerRecoveryRequest(BaseModel):
    sprint_id: UUID
    blocker: str


class AIBlockerRecoveryResponse(BaseModel):
    unblock_steps: list[str]
    progress_anyway_steps: list[str]
    suggested_next_step: str
