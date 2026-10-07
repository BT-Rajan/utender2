"""offer shortlist

Stage 6.12: offers the owner's side shortlisted while evaluating
(offer_shortlist) -- private to the owner side; not an award.

Downgrade drops the shortlist. It is refused while any offer is shortlisted,
unless ALLOW_SHORTLIST_LOSS=1 is set.

Revision ID: 0047
Revises: 0046
Create Date: 2026-10-07

"""
import os

import sqlalchemy as sa
from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offer_shortlist",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("offer_id", sa.String(36), sa.ForeignKey("offers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("offer_revision", sa.Integer(), nullable=False),
        sa.Column("material_revision", sa.Integer(), nullable=False),
        sa.Column("added_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("offer_id"),
    )
    op.create_index("ix_offer_shortlist_project_id", "offer_shortlist", ["project_id"])


def downgrade() -> None:
    held = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM offer_shortlist")).scalar()
    if held and os.environ.get("ALLOW_SHORTLIST_LOSS") != "1":
        raise RuntimeError(f"{held} shortlisted offer(s) would be lost by this downgrade. Set ALLOW_SHORTLIST_LOSS=1 to proceed anyway.")
    op.drop_table("offer_shortlist")  # its indexes go with it
