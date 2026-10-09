"""audit created_at index

Stage 9.9: the metrics' period queries read the audit trail by time.

Revision ID: 0064
Revises: 0063
Create Date: 2026-10-08

"""
from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
