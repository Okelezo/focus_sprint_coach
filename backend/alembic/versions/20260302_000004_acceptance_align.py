"""acceptance alignment

Revision ID: 20260302_000004
Revises: 20260302_000003
Create Date: 2026-03-02

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260302_000004"
down_revision: Union[str, None] = "20260302_000003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Column type alignment (TEXT)
    op.alter_column("users", "email", type_=sa.Text())
    op.alter_column("users", "password_hash", type_=sa.Text())

    op.alter_column("tasks", "title", type_=sa.Text())
    op.alter_column("microsteps", "text", type_=sa.Text())

    op.alter_column("sprint_events", "payload", server_default=sa.text("'{}'::jsonb"))

    op.alter_column("sprint_reflections", "next_step", type_=sa.Text())

    # sprints.status: enum -> text
    op.execute("ALTER TABLE sprints ALTER COLUMN status TYPE text USING status::text")
    op.execute("ALTER TABLE sprints ALTER COLUMN status SET DEFAULT 'active'")
    op.execute("ALTER TABLE sprints ALTER COLUMN started_at SET DEFAULT now()")

    # sprint_events.type: enum -> text
    op.execute("ALTER TABLE sprint_events ALTER COLUMN type TYPE text USING type::text")

    # sprint_reflections.outcome: enum -> text
    op.execute(
        "ALTER TABLE sprint_reflections ALTER COLUMN outcome TYPE text USING outcome::text"
    )

    # Drop old enum types (no longer used)
    op.execute("DROP TYPE IF EXISTS sprint_status")
    op.execute("DROP TYPE IF EXISTS sprint_event_type")
    op.execute("DROP TYPE IF EXISTS sprint_reflection_outcome")

    # CHECK constraints
    op.create_check_constraint(
        "ck_sprints_status_allowed",
        "sprints",
        "status IN ('active','completed','abandoned')",
    )
    op.create_check_constraint(
        "ck_sprints_duration_minutes_gt_0",
        "sprints",
        "duration_minutes > 0",
    )
    op.create_check_constraint(
        "ck_sprint_events_type_allowed",
        "sprint_events",
        "type IN ('distraction','note','blocker')",
    )
    op.create_check_constraint(
        "ck_sprint_reflections_outcome_allowed",
        "sprint_reflections",
        "outcome IN ('done','blocked','distracted')",
    )

    # ai_usage: count -> calls, remove extra columns
    with op.batch_alter_table("ai_usage") as batch:
        batch.alter_column("count", new_column_name="calls")
        batch.alter_column("calls", server_default=sa.text("0"))
        batch.drop_column("created_at")
        batch.drop_column("updated_at")

    # Indexes: drop old and recreate to match acceptance spec
    for ix, table in [
        ("ix_tasks_user_id", "tasks"),
        ("ix_microsteps_task_id", "microsteps"),
        ("ix_sprints_user_id", "sprints"),
        ("ix_sprints_task_id", "sprints"),
        ("ix_sprint_events_sprint_id", "sprint_events"),
        ("ix_sprint_reflections_sprint_id", "sprint_reflections"),
        ("ix_ai_usage_user_id", "ai_usage"),
    ]:
        try:
            op.drop_index(ix, table_name=table)
        except Exception:
            # Index may not exist depending on environment
            pass

    # Create acceptance indexes (with DESC where required)
    op.execute("CREATE INDEX IF NOT EXISTS ix_tasks_user_id_created_at_desc ON tasks (user_id, created_at DESC)")
    op.create_index(
        "ix_microsteps_task_id_order_index",
        "microsteps",
        ["task_id", "order_index"],
        unique=False,
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sprints_user_id_started_at_desc ON sprints (user_id, started_at DESC)"
    )
    op.create_index(
        "ix_sprint_events_sprint_id_created_at",
        "sprint_events",
        ["sprint_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_usage_user_id_day",
        "ai_usage",
        ["user_id", "day"],
        unique=False,
    )


def downgrade() -> None:
    # Downgrade not implemented for acceptance alignment.
    raise RuntimeError("downgrade_not_supported")
