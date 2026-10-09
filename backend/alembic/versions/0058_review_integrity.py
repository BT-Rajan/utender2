"""review integrity

Stage 8.5: database-level guarantees for reviews -- a review is one of the
two directions (ck_review_direction) and between two different parties
(ck_review_two_parties), alongside the existing rating range and the one
review per transaction per direction.

Revision ID: 0058
Revises: 0057
Create Date: 2026-10-08

"""
from alembic import op

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("reviews") as batch:
        batch.create_check_constraint("ck_review_direction", "direction IN ('owner_to_provider', 'provider_to_owner')")
        batch.create_check_constraint("ck_review_two_parties", "owner_id <> service_provider_id")


def downgrade() -> None:
    with op.batch_alter_table("reviews") as batch:
        batch.drop_constraint("ck_review_two_parties", type_="check")
        batch.drop_constraint("ck_review_direction", type_="check")
