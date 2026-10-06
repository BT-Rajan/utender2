"""requirement-specific provider eligibility

Stage 3.9. projects.provider_eligibility (JSON): who may respond to the
requirement beyond platform verification -- organizations only, and/or
platform-approved provider documents (ids from document_requirements).
NULL = every verified provider with active access.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-06

"""
import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("provider_eligibility", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "provider_eligibility")
