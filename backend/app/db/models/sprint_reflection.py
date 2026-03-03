import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SprintReflectionOutcome(str, enum.Enum):
    done = "done"
    blocked = "blocked"
    distracted = "distracted"


class SprintReflection(Base):
    __tablename__ = "sprint_reflections"
    __table_args__ = (
        UniqueConstraint("sprint_id", name="uq_sprint_reflection_sprint"),
        CheckConstraint(
            "outcome IN ('done','blocked','distracted')",
            name="ck_sprint_reflections_outcome_allowed",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    sprint_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sprints.id", ondelete="CASCADE"),
        nullable=False,
    )
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_step: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sprint = relationship("Sprint", back_populates="reflection")
