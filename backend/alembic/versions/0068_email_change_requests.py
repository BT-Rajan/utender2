"""email_change_requests -- verify-by-code change of a person's sign-in email

A code is sent to the person's current address; confirming it switches the
account to the new one (which then has to be verified in turn).

Revision ID: 0068
Revises: 0067
Create Date: 2026-10-10
"""
import sqlalchemy as sa
from alembic import op

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_change_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("new_email", sa.String(255), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("consumed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_email_change_user", "email_change_requests", ["user_id"])


def downgrade() -> None:
    op.drop_table("email_change_requests")
