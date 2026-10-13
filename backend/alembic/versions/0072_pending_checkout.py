"""service_provider_profiles.stripe_checkout_session_id: the checkout a
provider last started, expired before another starts, so two checkouts can't
both create a subscription (provider-journey review).

Revision ID: 0072
Revises: 0071
Create Date: 2026-10-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("service_provider_profiles", sa.Column("stripe_checkout_session_id", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("service_provider_profiles", "stripe_checkout_session_id")
