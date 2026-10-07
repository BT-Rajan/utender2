"""tender and commercial rules on a requirement

Stage 3.10. projects gains:
  * questions_allowed (default true) and questions_deadline (NULL = until
    offers close): whether and until when providers may ask questions;
  * commercial_terms and bidder_instructions: the owner's own conditions
    and instructions for providers.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-07

"""
import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("questions_allowed", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("projects", sa.Column("questions_deadline", sa.DateTime(), nullable=True))
    op.add_column("projects", sa.Column("commercial_terms", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("bidder_instructions", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "bidder_instructions")
    op.drop_column("projects", "commercial_terms")
    op.drop_column("projects", "questions_deadline")
    op.drop_column("projects", "questions_allowed")
