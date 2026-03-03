"""add_task_scheduling

Revision ID: ff464a83fce7
Revises: 20260302_000007
Create Date: 2026-03-03 01:22:30.387003

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ff464a83fce7'
down_revision: Union[str, None] = '20260302_000007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('scheduled_date', sa.Date(), nullable=True))
    op.add_column('tasks', sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_tasks_user_scheduled_date', 'tasks', ['user_id', 'scheduled_date'])


def downgrade() -> None:
    op.drop_index('ix_tasks_user_scheduled_date', table_name='tasks')
    op.drop_column('tasks', 'completed_at')
    op.drop_column('tasks', 'scheduled_date')
