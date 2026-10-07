"""organization invitations

An organization's representative invites a colleague by email (account or
not); they join only by accepting, signed in with that email.

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-07

"""
import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_invitations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.Enum("owner", "service_provider", "admin", name="userrole"), nullable=False),
        sa.Column("position", sa.String(150), nullable=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("invited_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_organization_invitations_organization_id", "organization_invitations", ["organization_id"])
    op.create_index("ix_organization_invitations_email", "organization_invitations", ["email"])


def downgrade() -> None:
    op.drop_table("organization_invitations")
