"""organization sharing

Records created while acting for an organization carry its id, so every
current member works with them (services.team): projects, offers, offer
documents and clarifications gain organization_id. One offer (and one
attachment per requested label) per organization per requirement.
Existing rows take the organization their creator currently belongs to.

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-07

"""
import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

_TABLES = [("projects", "owner_id"), ("offers", "service_provider_id"), ("offer_documents", "service_provider_id"), ("clarifications", "service_provider_id")]


def upgrade() -> None:
    for table, creator in _TABLES:
        op.add_column(table, sa.Column("organization_id", sa.String(36), nullable=True))
        op.create_index(f"ix_{table}_organization_id", table, ["organization_id"])
        op.create_foreign_key(f"fk_{table}_organization_id", table, "organizations", ["organization_id"], ["id"], ondelete="SET NULL")
        op.execute(
            f"UPDATE {table} SET organization_id = ("
            f"SELECT m.organization_id FROM organization_memberships m WHERE m.user_id = {table}.{creator} LIMIT 1)"
        )
    op.create_unique_constraint("uq_project_organization", "offers", ["project_id", "organization_id"])
    op.create_unique_constraint("uq_offer_document_org_label", "offer_documents", ["project_id", "organization_id", "label"])


def downgrade() -> None:
    op.drop_constraint("uq_offer_document_org_label", "offer_documents", type_="unique")
    op.drop_constraint("uq_project_organization", "offers", type_="unique")
    for table, _creator in reversed(_TABLES):
        op.drop_constraint(f"fk_{table}_organization_id", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_organization_id", table_name=table)
        op.drop_column(table, "organization_id")
