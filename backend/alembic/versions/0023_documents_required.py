"""documents required to price

Stage 3.12 follow-up: projects.documents_required -- the owner's explicit
statement that providers need the attached documents to price, which the
quality gate enforces (replacing a guess from the scope's wording).

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-07

"""
import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("documents_required", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("projects", "documents_required")
