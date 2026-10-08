"""review moderation

Stage 8.15: a party may report a review about it, or the response to its own
review (review_reports, one per review and target); an admin keeps or hides
what was reported. Hiding keeps the row: reviews.hidden_at (the review is no
longer shown or counted) and reviews.response_hidden_at (the response is no
longer shown).

Downgrade is refused while any report or hidden review/response exists,
unless ALLOW_REVIEW_LOSS=1 is set.

Revision ID: 0060
Revises: 0059
Create Date: 2026-10-08

"""
import os

import sqlalchemy as sa
from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("reviews") as batch:
        batch.add_column(sa.Column("hidden_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("response_hidden_at", sa.DateTime(), nullable=True))
    op.create_table(
        "review_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("review_id", sa.String(36), sa.ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target", sa.String(16), nullable=False),
        sa.Column("reporter_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.UniqueConstraint("review_id", "target", name="uq_review_report_target"),
        sa.CheckConstraint("target IN ('review', 'response')", name="ck_review_report_target"),
        sa.CheckConstraint("status IN ('open', 'kept', 'hidden')", name="ck_review_report_status"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    held = bind.execute(sa.text(
        "SELECT (SELECT COUNT(*) FROM review_reports) + (SELECT COUNT(*) FROM reviews WHERE hidden_at IS NOT NULL OR response_hidden_at IS NOT NULL)"
    )).scalar()
    if held and os.environ.get("ALLOW_REVIEW_LOSS") != "1":
        raise RuntimeError(f"{held} review report(s) or moderation decision(s) would be lost by this downgrade. Set ALLOW_REVIEW_LOSS=1 to proceed anyway.")
    op.drop_table("review_reports")
    with op.batch_alter_table("reviews") as batch:
        batch.drop_column("response_hidden_at")
        batch.drop_column("hidden_at")
