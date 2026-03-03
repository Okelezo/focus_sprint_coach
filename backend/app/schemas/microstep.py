from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MicroStepCreate(BaseModel):
    text: str
    order_index: int


class MicroStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    text: str
    order_index: int
