"""publication time

Stage 3.14: projects.published_at, set by the server in the transaction
that publishes a requirement. Requirements already open take their
creation time.

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-07

"""
import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("published_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE projects SET published_at = created_at WHERE status <> 'draft'")


def downgrade() -> None:
    op.drop_column("projects", "published_at")
