"""notifications: the owner side is told where its requirement stands

- offer_confirmed: a provider confirmed its offer still stands, so it can be
  considered for award;
- requirement_expired: the requirement reached its deadline without an offer.
(evaluation_ready, for offers closed at the deadline, was already allowed.)

Revision ID: 0070
Revises: 0069
Create Date: 2026-10-13
"""
from alembic import op

revision = "0070"
down_revision = "0069"
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
    "milestone_updated", "variation_updated", "review_received", "review_response",
    "agreement_terms_confirmed", "agreement_in_force", "agreement_terminated", "offer_confirmation_requested",
    "evaluation_started", "requirement_invitation",
]
_NEW = ["offer_confirmed", "requirement_expired"]


def _enum(values) -> str:
    return "ENUM(" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    if op.get_bind().dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES + _NEW)} NOT NULL")


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE type IN ('offer_confirmed', 'requirement_expired')")
    if op.get_bind().dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES)} NOT NULL")
