"""work completion

Stage 7.10: the whole work's completion on the agreement -- submitted as
complete by the winning provider, accepted or returned for correction by the
owner side (agreements.completion_*).

Downgrade drops the columns. It is refused while any completion is
recorded, unless ALLOW_COMPLETION_LOSS=1 is set.

Revision ID: 0054
Revises: 0053
Create Date: 2026-10-08

"""
import os

import sqlalchemy as sa
from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agreements", sa.Column("completion_status", sa.String(16), nullable=True))
    op.add_column("agreements", sa.Column("completion_submitted_at", sa.DateTime(), nullable=True))
    op.add_column("agreements", sa.Column("completion_submitted_by", sa.String(36), nullable=True))
    op.add_column("agreements", sa.Column("completion_note", sa.Text(), nullable=True))
    op.add_column("agreements", sa.Column("completion_decided_at", sa.DateTime(), nullable=True))
    op.add_column("agreements", sa.Column("completion_decided_by", sa.String(36), nullable=True))
    op.add_column("agreements", sa.Column("completion_decision_note", sa.Text(), nullable=True))
    op.create_foreign_key("fk_agreements_completion_submitted_by", "agreements", "users", ["completion_submitted_by"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_agreements_completion_decided_by", "agreements", "users", ["completion_decided_by"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    held = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM agreements WHERE completion_status IS NOT NULL")).scalar()
    if held and os.environ.get("ALLOW_COMPLETION_LOSS") != "1":
        raise RuntimeError(f"{held} recorded completion(s) would be lost by this downgrade. Set ALLOW_COMPLETION_LOSS=1 to proceed anyway.")
    op.execute("DELETE FROM execution_updates WHERE milestone_id IS NULL AND kind IN ('delivered', 'accepted', 'returned')")
    op.drop_constraint("fk_agreements_completion_decided_by", "agreements", type_="foreignkey")
    op.drop_constraint("fk_agreements_completion_submitted_by", "agreements", type_="foreignkey")
    for column in ("completion_decision_note", "completion_decided_by", "completion_decided_at", "completion_note",
                   "completion_submitted_by", "completion_submitted_at", "completion_status"):
        op.drop_column("agreements", column)
