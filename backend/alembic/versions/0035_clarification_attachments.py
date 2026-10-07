"""clarification attachments

Stage 4.7 follow-up: files attached to a question (by its asker's side) or to
its answer (by the owner's side), seen by whoever can see that question or
answer.

Revision ID: 0035
Revises: 0034
Create Date: 2026-10-07

"""
import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clarification_attachments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("clarification_id", sa.String(36), sa.ForeignKey("clarifications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("part", sa.String(10), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_clarification_attachments_clarification_id", "clarification_attachments", ["clarification_id"])


def downgrade() -> None:
    # Dropping the table drops its index too (MySQL won't drop an index a
    # foreign key still needs on its own).
    op.drop_table("clarification_attachments")
