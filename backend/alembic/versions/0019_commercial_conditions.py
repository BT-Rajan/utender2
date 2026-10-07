"""structured commercial conditions

Stage 3.10 follow-up. projects.commercial_conditions (JSON): offer validity,
payment stages, retention and warranty as fields. projects.commercial_terms
stays as the owner's "other conditions" text.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-07

"""
import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("commercial_conditions", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "commercial_conditions")
