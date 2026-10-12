"""email_change_requests: match the model (CI's `alembic check` failed on 0068)

created_at becomes NOT NULL (it always has a server default), and the user_id
index takes the name the model's index=True gives it.

Revision ID: 0069
Revises: 0068
Create Date: 2026-10-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None


def _rename_index(old: str, new: str) -> None:
    # On MySQL the index backs the user_id foreign key, so it can't be dropped
    # before its replacement exists -- rename it in place instead.
    if op.get_bind().dialect.name == "mysql":
        op.execute(f"ALTER TABLE email_change_requests RENAME INDEX {old} TO {new}")
    else:
        op.drop_index(old, table_name="email_change_requests")
        op.create_index(new, "email_change_requests", ["user_id"])


def upgrade() -> None:
    op.execute("UPDATE email_change_requests SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
    op.alter_column(
        "email_change_requests", "created_at",
        existing_type=sa.DateTime, existing_server_default=sa.func.now(), nullable=False,
    )
    _rename_index("idx_email_change_user", "ix_email_change_requests_user_id")


def downgrade() -> None:
    _rename_index("ix_email_change_requests_user_id", "idx_email_change_user")
    op.alter_column(
        "email_change_requests", "created_at",
        existing_type=sa.DateTime, existing_server_default=sa.func.now(), nullable=True,
    )
