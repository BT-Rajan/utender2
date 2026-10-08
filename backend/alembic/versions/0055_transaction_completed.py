"""transaction completed

Stage 7.11: the owner's acceptance of the whole work closes the transaction:
agreements.status becomes "completed" with completed_at. Agreements whose
work was already accepted (Stage 7.10) are completed at their acceptance
time.

Downgrade puts completed agreements back to "active" (their acceptance is
kept) and drops completed_at.

Revision ID: 0055
Revises: 0054
Create Date: 2026-10-08

"""
import sqlalchemy as sa
from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agreements", sa.Column("completed_at", sa.DateTime(), nullable=True))
    op.execute(
        "UPDATE agreements SET status = 'completed', completed_at = completion_decided_at "
        "WHERE completion_status = 'accepted' AND status = 'active'"
    )


def downgrade() -> None:
    op.execute("UPDATE agreements SET status = 'active' WHERE status = 'completed'")
    op.drop_column("agreements", "completed_at")
