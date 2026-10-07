"""offer submitted at

Stage 5.11: offers.submitted_at -- when an offer was first put forward. Since
Stage 5.2 an offer row starts as a draft, so created_at is when preparation
began; offers already submitted take their created_at.

Revision ID: 0043
Revises: 0042
Create Date: 2026-10-07

"""
import sqlalchemy as sa
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("offers", sa.Column("submitted_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE offers SET submitted_at = created_at WHERE status <> 'draft'")


def downgrade() -> None:
    op.drop_column("offers", "submitted_at")
