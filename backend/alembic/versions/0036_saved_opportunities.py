"""saved opportunities

Stage 4.8: opportunities a provider marked to come back to -- one row per
provider stakeholder and requirement, removed with either.

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-07

"""
import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_opportunities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("service_provider_id", sa.String(36), sa.ForeignKey("service_provider_profiles.user_id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("saved_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("project_id", "service_provider_id", name="uq_saved_opportunity"),
    )


def downgrade() -> None:
    op.drop_table("saved_opportunities")
