"""participations

Stage 4.9: a provider's decision to take part in a requirement -- one per
provider stakeholder and requirement, with the version they decided on.
Offers already submitted count as participation: backfilled from them.

Revision ID: 0037
Revises: 0036
Create Date: 2026-10-07

"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "participations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("service_provider_id", sa.String(36), sa.ForeignKey("service_provider_profiles.user_id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("started_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("seen_material_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("project_id", "service_provider_id", name="uq_participation"),
    )
    bind = op.get_bind()
    for project_id, provider_id, organization_id, revision_seen, created in bind.execute(
        sa.text("SELECT project_id, service_provider_id, organization_id, based_on_material_revision, created_at FROM offers")
    ).fetchall():
        bind.execute(
            sa.text(
                "INSERT INTO participations (id, project_id, service_provider_id, organization_id, seen_material_revision, started_at)"
                " VALUES (:i, :p, :s, :o, :r, :t)"
            ),
            {"i": str(uuid.uuid4()), "p": project_id, "s": provider_id, "o": organization_id, "r": revision_seen or 0, "t": created},
        )


def downgrade() -> None:
    op.drop_table("participations")
