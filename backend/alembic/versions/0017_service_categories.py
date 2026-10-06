"""service categories; structured provider services; category on requirements

Stage 3.9 follow-up.
  * service_categories: the platform's admin-managed list of types of work
    (starts empty; nothing hard-coded).
  * projects.category_id: the category a requirement is filed under
    (projects.trade keeps the shown name).
  * service_provider_profiles.service_categories / service_governorates
    (JSON): what a provider offers and where, so an owner can require a
    match.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-06

"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_categories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.add_column("projects", sa.Column("category_id", sa.String(36), nullable=True))
    op.create_index("ix_projects_category_id", "projects", ["category_id"])
    op.create_foreign_key(
        "fk_projects_category_id", "projects", "service_categories", ["category_id"], ["id"], ondelete="SET NULL"
    )
    op.add_column("service_provider_profiles", sa.Column("service_categories", sa.JSON(), nullable=True))
    op.add_column("service_provider_profiles", sa.Column("service_governorates", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("service_provider_profiles", "service_governorates")
    op.drop_column("service_provider_profiles", "service_categories")
    op.drop_constraint("fk_projects_category_id", "projects", type_="foreignkey")
    op.drop_index("ix_projects_category_id", table_name="projects")
    op.drop_column("projects", "category_id")
    op.drop_table("service_categories")
