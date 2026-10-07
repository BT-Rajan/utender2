"""closure reason

Stage 3.16: projects.closure_reason -- why a requirement ended without a
U-Tender award, within its terminal status (no new states).

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-07

"""
import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("closure_reason", sa.String(30), nullable=True))
    # Requirements already marked no-award were decided after offers closed.
    op.execute("UPDATE projects SET closure_reason = 'no_suitable_offer' WHERE status = 'no_award'")
    op.execute("UPDATE projects SET closure_reason = 'other' WHERE status = 'canceled'")


def downgrade() -> None:
    op.drop_column("projects", "closure_reason")
