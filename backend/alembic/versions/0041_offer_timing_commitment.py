"""offer timing commitment

Stage 5.5: the provider's execution commitment on the offer (and its
revision history), in the requirement's own terms (Stage 3.7): a proposed
start date, and a completion date or a duration in days.

Revision ID: 0041
Revises: 0040
Create Date: 2026-10-07

"""
import sqlalchemy as sa
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

_TABLES = ("offers", "offer_revisions")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("proposed_start_date", sa.Date(), nullable=True))
        op.add_column(table, sa.Column("proposed_completion_date", sa.Date(), nullable=True))
        op.add_column(table, sa.Column("proposed_duration_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "proposed_duration_days")
        op.drop_column(table, "proposed_completion_date")
        op.drop_column(table, "proposed_start_date")
