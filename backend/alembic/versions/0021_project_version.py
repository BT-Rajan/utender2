"""requirement version counter

Stage 3.11 follow-up: projects.version, incremented on every save and
checked (If-Match) under the row lock, replacing the whole-second
updated_at as the concurrency check.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-07

"""
import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("projects", "version")
