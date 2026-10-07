"""participation per organization

Stage 5.1: starting an offer creates one offer workspace per organization and
requirement, enforced by the database as offers are -- not only by the acting
profile. Any duplicates are folded into the earliest first.

Revision ID: 0038
Revises: 0037
Create Date: 2026-10-07

"""
import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, project_id, organization_id FROM participations"
            " WHERE organization_id IS NOT NULL ORDER BY started_at, id"
        )
    ).fetchall()
    kept: set[tuple[str, str]] = set()
    for row_id, project_id, organization_id in rows:
        if (project_id, organization_id) in kept:
            bind.execute(sa.text("DELETE FROM participations WHERE id = :i"), {"i": row_id})
        else:
            kept.add((project_id, organization_id))
    op.create_unique_constraint("uq_participation_organization", "participations", ["project_id", "organization_id"])


def downgrade() -> None:
    op.drop_constraint("uq_participation_organization", "participations", type_="unique")
