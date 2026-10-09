"""email failures

Stage 9.5: a durable record of emails the platform couldn't send, so the
operator overview can say delivery is failing instead of assuming it works.

Revision ID: 0062
Revises: 0061
Create Date: 2026-10-08

"""
import sqlalchemy as sa
from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_failures",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("recipient", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_email_failures_created_at", "email_failures", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_email_failures_created_at", table_name="email_failures")
    op.drop_table("email_failures")
