"""two-way reviews

Stage 8.4: reviews in both directions of a completed transaction -- the
owner side reviewing the winning provider (as before) and the winning
provider reviewing the owner. reviews gains direction and reviewer_id; one
review per transaction per direction (uq_review_project_direction replaces
uq_review_project); owner_id now always names the requirement's owner party
(projects.owner_id) -- existing rows keep their writer in reviewer_id. Adds the
review_received notification.

Downgrade is refused while any provider-to-owner review exists, unless
ALLOW_REVIEW_LOSS=1 is set.

Revision ID: 0057
Revises: 0056
Create Date: 2026-10-08

"""
import os

import sqlalchemy as sa
from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None

_TYPES = [
    "document_rejected", "document_approved", "verification_activated", "payment_activated", "payment_failed",
    "payment_override_granted", "payment_override_revoked", "service_provider_suspended", "service_provider_reactivated",
    "owner_verification_activated", "owner_document_rejected", "owner_document_approved", "owner_suspended",
    "owner_reactivated", "document_expiring", "tender_amendment", "drawing_revised", "clarification_asked",
    "clarification_answered", "bid_submitted", "bid_revised", "bid_withdrawn", "deadline_approaching",
    "tender_closed", "evaluation_ready", "award_won", "award_lost", "tender_cancelled", "tender_no_award",
    "project_suspended", "project_reactivated", "offer_suspended", "offer_reactivated",
    "verification_changes_requested", "verification_rejected", "new_requirement",
    "tender_paused", "tender_resumed", "requirement_ended", "clarification_shared",
    "offer_clarification_requested", "offer_clarification_answered", "work_started", "execution_updated",
    "milestone_updated", "variation_updated",
]
_NEW = ["review_received"]


def _enum(values) -> str:
    return "ENUM(" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column("reviews", sa.Column("direction", sa.String(24), nullable=False, server_default="owner_to_provider"))
    op.add_column("reviews", sa.Column("reviewer_id", sa.String(36), nullable=True))
    op.create_foreign_key("fk_reviews_reviewer", "reviews", "users", ["reviewer_id"], ["id"], ondelete="SET NULL")
    bind.execute(sa.text("UPDATE reviews SET reviewer_id = owner_id"))
    bind.execute(sa.text("UPDATE reviews SET owner_id = (SELECT p.owner_id FROM projects p WHERE p.id = reviews.project_id)"))
    # The new key first: on MySQL it then carries the project_id foreign key's index.
    with op.batch_alter_table("reviews") as batch:
        batch.create_unique_constraint("uq_review_project_direction", ["project_id", "direction"])
        batch.drop_constraint("uq_review_project", type_="unique")
    if bind.dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES + _NEW)} NOT NULL")


def downgrade() -> None:
    bind = op.get_bind()
    held = bind.execute(sa.text("SELECT COUNT(*) FROM reviews WHERE direction <> 'owner_to_provider'")).scalar()
    if held and os.environ.get("ALLOW_REVIEW_LOSS") != "1":
        raise RuntimeError(f"{held} provider-to-owner review(s) would be lost by this downgrade. Set ALLOW_REVIEW_LOSS=1 to proceed anyway.")
    bind.execute(sa.text("DELETE FROM reviews WHERE direction <> 'owner_to_provider'"))
    bind.execute(sa.text("DELETE FROM notifications WHERE type = 'review_received'"))
    if bind.dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES)} NOT NULL")
    bind.execute(sa.text("UPDATE reviews SET owner_id = reviewer_id WHERE reviewer_id IS NOT NULL"))
    with op.batch_alter_table("reviews") as batch:
        batch.create_unique_constraint("uq_review_project", ["project_id"])
        batch.drop_constraint("uq_review_project_direction", type_="unique")
    op.drop_constraint("fk_reviews_reviewer", "reviews", type_="foreignkey")
    op.drop_column("reviews", "reviewer_id")
    op.drop_column("reviews", "direction")
