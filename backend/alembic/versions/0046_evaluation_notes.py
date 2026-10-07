"""evaluation notes

Stage 6.11: the owner side's private evaluation notes, on a requirement or
on one of its offers (evaluation_notes). Visible to the requirement's owner
side only; edited or removed by their author.

Downgrade drops the notes. It is refused while any exist, unless
ALLOW_NOTE_LOSS=1 is set.

Revision ID: 0046
Revises: 0045
Create Date: 2026-10-07

"""
import os

import sqlalchemy as sa
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluation_notes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("offer_id", sa.String(36), sa.ForeignKey("offers.id", ondelete="CASCADE"), nullable=True),
        sa.Column("author_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("client_token", sa.String(64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("author_id", "client_token", name="uq_evaluation_note_client_token"),
    )
    op.create_index("ix_evaluation_notes_project_id", "evaluation_notes", ["project_id"])
    op.create_index("ix_evaluation_notes_offer_id", "evaluation_notes", ["offer_id"])


def downgrade() -> None:
    held = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM evaluation_notes")).scalar()
    if held and os.environ.get("ALLOW_NOTE_LOSS") != "1":
        raise RuntimeError(f"{held} evaluation note(s) would be deleted by this downgrade. Set ALLOW_NOTE_LOSS=1 to proceed anyway.")
    op.drop_table("evaluation_notes")  # its indexes go with it (MySQL won't drop one a foreign key needs first)
