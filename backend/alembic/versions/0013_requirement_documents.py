"""requirement document type and essential flag

Stage 3.6. Requirement files (project_drawings) gain category -- drawing,
boq, specification, photo, site or other (see services/drawings.py) -- and
is_required: whether providers need the file to price the work or it is
supplementary. Existing files were all uploaded as drawings, so they become
category 'drawing', required.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-06

"""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_drawings", sa.Column("category", sa.String(20), nullable=False, server_default="drawing"))
    op.add_column("project_drawings", sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("project_drawings", "is_required")
    op.drop_column("project_drawings", "category")
