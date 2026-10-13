"""service_provider_documents.previous_file_path / previous_expires_on: a
renewal of a still-valid approved qualification keeps the approval it renews
counting until the renewal is decided (provider-journey review).

Revision ID: 0073
Revises: 0072
Create Date: 2026-10-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("service_provider_documents", sa.Column("previous_file_path", sa.String(500), nullable=True))
    op.add_column("service_provider_documents", sa.Column("previous_expires_on", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("service_provider_documents", "previous_expires_on")
    op.drop_column("service_provider_documents", "previous_file_path")
