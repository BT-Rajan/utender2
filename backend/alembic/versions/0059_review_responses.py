"""review responses

Stage 8.9: the reviewed side's one, final response to a review, kept beside
it on the review row (response, response_at, responded_by) -- the review's
rating, comment and parties never change. Adds the review_response
notification.

Downgrade is refused while any response exists, unless
ALLOW_REVIEW_LOSS=1 is set.

Revision ID: 0059
Revises: 0058
Create Date: 2026-10-08

"""
import os

import sqlalchemy as sa
from alembic import op

revision = "0059"
down_revision = "0058"
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
    "milestone_updated", "variation_updated", "review_received",
]
_NEW = ["review_response"]


def _enum(values) -> str:
    return "ENUM(" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table("reviews") as batch:
        batch.add_column(sa.Column("response", sa.Text(), nullable=True))
        batch.add_column(sa.Column("response_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("responded_by", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_reviews_responded_by", "users", ["responded_by"], ["id"], ondelete="SET NULL")
        batch.create_check_constraint(
            "ck_review_response_complete",
            "(response IS NULL AND response_at IS NULL) OR (response IS NOT NULL AND response_at IS NOT NULL)",
        )
    if bind.dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES + _NEW)} NOT NULL")


def downgrade() -> None:
    bind = op.get_bind()
    held = bind.execute(sa.text("SELECT COUNT(*) FROM reviews WHERE response IS NOT NULL")).scalar()
    if held and os.environ.get("ALLOW_REVIEW_LOSS") != "1":
        raise RuntimeError(f"{held} review response(s) would be lost by this downgrade. Set ALLOW_REVIEW_LOSS=1 to proceed anyway.")
    bind.execute(sa.text("DELETE FROM notifications WHERE type = 'review_response'"))
    if bind.dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES)} NOT NULL")
    with op.batch_alter_table("reviews") as batch:
        batch.drop_constraint("ck_review_response_complete", type_="check")
        batch.drop_constraint("fk_reviews_responded_by", type_="foreignkey")
        batch.drop_column("responded_by")
        batch.drop_column("response_at")
        batch.drop_column("response")
