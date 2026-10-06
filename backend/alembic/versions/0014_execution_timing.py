"""expected work timing

Stage 3.7. When the owner expects the work to happen -- separate from the
response deadline (projects.bid_deadline, unchanged and still the only
deadline the tender system enforces): an optional expected start date and
either an expected completion date or a duration in days.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-06

"""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("expected_start_date", sa.Date(), nullable=True))
    op.add_column("projects", sa.Column("expected_completion_date", sa.Date(), nullable=True))
    op.add_column("projects", sa.Column("expected_duration_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "expected_duration_days")
    op.drop_column("projects", "expected_completion_date")
    op.drop_column("projects", "expected_start_date")
