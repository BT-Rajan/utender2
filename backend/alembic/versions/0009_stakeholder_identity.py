"""stakeholder identity: organizations, memberships, and who each profile represents

Step 3 of the user journey. A login (users) is always a person. Each role
profile now records whether it represents that person (individual) or an
organization, and organization-based profiles point at an organizations row
that the person belongs to through organization_memberships.

Backfill for existing accounts, so no one is asked to re-establish:
  * owner profiles -> individual (the owner verification checklist is
    personal: civil ID, proof of property ownership);
  * service provider profiles whose company_name differs from the person's
    own name -> organization named company_name, with that person as its
    authorized representative (admin); the rest -> individual.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-06

"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

_PROFILES = ("owner_profiles", "service_provider_profiles")


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("legal_name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "organization_memberships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.Enum("admin", "member", name="membershiprole"), nullable=False),
        sa.Column("position", sa.String(150), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_organization_member"),
    )
    op.create_index("ix_organization_memberships_organization_id", "organization_memberships", ["organization_id"])
    op.create_index("ix_organization_memberships_user_id", "organization_memberships", ["user_id"])

    for table in _PROFILES:
        op.add_column(table, sa.Column("stakeholder_type", sa.Enum("individual", "organization", name="stakeholdertype"), nullable=True))
        op.add_column(table, sa.Column("organization_id", sa.String(36), nullable=True))
        op.create_unique_constraint(f"uq_{table}_organization_id", table, ["organization_id"])
        op.create_foreign_key(
            f"fk_{table}_organization_id", table, "organizations", ["organization_id"], ["id"], ondelete="RESTRICT"
        )

    conn = op.get_bind()
    conn.execute(sa.text("UPDATE owner_profiles SET stakeholder_type = 'individual'"))
    rows = conn.execute(
        sa.text(
            "SELECT p.user_id, p.company_name, u.full_name FROM service_provider_profiles p JOIN users u ON u.id = p.user_id"
        )
    ).all()
    for user_id, company_name, full_name in rows:
        if company_name and company_name.strip().lower() != (full_name or "").strip().lower():
            org_id = str(uuid.uuid4())
            conn.execute(sa.text("INSERT INTO organizations (id, legal_name) VALUES (:id, :name)"), {"id": org_id, "name": company_name.strip()})
            conn.execute(
                sa.text("INSERT INTO organization_memberships (id, organization_id, user_id, role) VALUES (:id, :org, :user, 'admin')"),
                {"id": str(uuid.uuid4()), "org": org_id, "user": user_id},
            )
            conn.execute(
                sa.text("UPDATE service_provider_profiles SET stakeholder_type = 'organization', organization_id = :org WHERE user_id = :user"),
                {"org": org_id, "user": user_id},
            )
        else:
            conn.execute(sa.text("UPDATE service_provider_profiles SET stakeholder_type = 'individual' WHERE user_id = :user"), {"user": user_id})


def downgrade() -> None:
    for table in _PROFILES:
        op.drop_constraint(f"fk_{table}_organization_id", table, type_="foreignkey")
        op.drop_constraint(f"uq_{table}_organization_id", table, type_="unique")
        op.drop_column(table, "organization_id")
        op.drop_column(table, "stakeholder_type")
    op.drop_table("organization_memberships")
    op.drop_table("organizations")
