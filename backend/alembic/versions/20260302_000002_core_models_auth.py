"""core models + auth

Revision ID: 20260302_000002
Revises: 20260302_000001
Create Date: 2026-03-02

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260302_000002"
down_revision: Union[str, None] = "20260302_000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.execute("DROP TABLE IF EXISTS sprints CASCADE")

    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "tasks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_tasks_user_id", "tasks", ["user_id"], unique=False)

    op.create_table(
        "microsteps",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("task_id", "order_index", name="uq_microsteps_task_order"),
    )
    op.create_index("ix_microsteps_task_id", "microsteps", ["task_id"], unique=False)

    sprint_status = postgresql.ENUM(
        "active",
        "completed",
        "abandoned",
        name="sprint_status",
        create_type=False,
    )
    sprint_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "sprints",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sprint_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_sprints_user_id", "sprints", ["user_id"], unique=False)
    op.create_index("ix_sprints_task_id", "sprints", ["task_id"], unique=False)

    sprint_event_type = postgresql.ENUM(
        "distraction",
        "note",
        "blocker",
        name="sprint_event_type",
        create_type=False,
    )
    sprint_event_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "sprint_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("sprint_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sprint_event_type, nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["sprint_id"], ["sprints.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_sprint_events_sprint_id", "sprint_events", ["sprint_id"], unique=False)

    sprint_reflection_outcome = postgresql.ENUM(
        "done",
        "blocked",
        "distracted",
        name="sprint_reflection_outcome",
        create_type=False,
    )
    sprint_reflection_outcome.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "sprint_reflections",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("sprint_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outcome", sprint_reflection_outcome, nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("next_step", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["sprint_id"], ["sprints.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("sprint_id", name="uq_sprint_reflection_sprint"),
    )
    op.create_index(
        "ix_sprint_reflections_sprint_id",
        "sprint_reflections",
        ["sprint_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_sprint_reflections_sprint_id", table_name="sprint_reflections")
    op.drop_table("sprint_reflections")
    op.drop_index("ix_sprint_events_sprint_id", table_name="sprint_events")
    op.drop_table("sprint_events")
    op.drop_index("ix_sprints_task_id", table_name="sprints")
    op.drop_index("ix_sprints_user_id", table_name="sprints")
    op.drop_table("sprints")
    op.drop_index("ix_microsteps_task_id", table_name="microsteps")
    op.drop_table("microsteps")
    op.drop_index("ix_tasks_user_id", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    postgresql.ENUM(name="sprint_reflection_outcome").drop(bind, checkfirst=True)
    postgresql.ENUM(name="sprint_event_type").drop(bind, checkfirst=True)
    postgresql.ENUM(name="sprint_status").drop(bind, checkfirst=True)
