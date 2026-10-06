"""requirement governorate and area

Stage 3.5. Where the work is, at the level a provider uses to judge
relevance and travel: projects.governorate (one of Kuwait's six, see
app/services/locations.py) and projects.area. Listings show these; the exact
address (projects.address) stays on the full requirement. Existing
requirements have neither until their owner adds them.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-06

"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("governorate", sa.String(40), nullable=True))
    op.add_column("projects", sa.Column("area", sa.String(100), nullable=True))
    op.create_index("ix_projects_governorate", "projects", ["governorate"])


def downgrade() -> None:
    op.drop_index("ix_projects_governorate", table_name="projects")
    op.drop_column("projects", "area")
    op.drop_column("projects", "governorate")
