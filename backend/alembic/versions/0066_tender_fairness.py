"""tender fairness: offer validity, withdrawals, ended offers

Batch B (business-logic fixes):
- offers.validity_confirmed_at: when the provider last confirmed, after
  offers closed, that its offer still stands (price and terms) -- the offer
  is valid for the requirement's validity period from then (or from the
  close);
- offers.withdrawal_count: an offer withdrawn twice can't be put forward
  again on the same requirement;
- offer status "closed": a live offer on a requirement that ended without an
  award (cancelled or no award) is closed, not left "submitted";
- two notifications: the owner asks a provider to confirm its offer still
  stands, and bidders are told evaluation has started.

Revision ID: 0066
Revises: 0065
Create Date: 2026-10-09
"""
import sqlalchemy as sa
from alembic import op

revision = "0066"
down_revision = "0065"
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
    "agreement_terms_confirmed", "agreement_in_force", "agreement_terminated",
]
_NEW_TYPES = ["offer_confirmation_requested", "evaluation_started"]
_STATUSES = ["draft", "submitted", "approved", "rejected", "withdrawn"]


def _enum(values) -> str:
    return "ENUM(" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.add_column("offers", sa.Column("validity_confirmed_at", sa.DateTime(), nullable=True))
    op.add_column("offers", sa.Column("withdrawal_count", sa.Integer(), nullable=False, server_default="0"))
    if op.get_bind().dialect.name == "mysql":
        op.execute(f"ALTER TABLE offers MODIFY COLUMN status {_enum(_STATUSES + ['closed'])} NOT NULL")
        op.execute(f"ALTER TABLE offer_revisions MODIFY COLUMN status {_enum(_STATUSES + ['closed'])} NOT NULL")
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES + _NEW_TYPES)} NOT NULL")
    # Offers left "submitted" on requirements that already ended without an award.
    op.execute(
        "UPDATE offers SET status = 'closed' WHERE status = 'submitted' AND project_id IN "
        "(SELECT id FROM projects WHERE status IN ('canceled', 'no_award'))"
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.execute("UPDATE offers SET status = 'submitted' WHERE status = 'closed'")
    op.execute("UPDATE offer_revisions SET status = 'submitted' WHERE status = 'closed'")
    op.execute("DELETE FROM notifications WHERE type IN ('offer_confirmation_requested', 'evaluation_started')")
    if bind.dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES)} NOT NULL")
        op.execute(f"ALTER TABLE offer_revisions MODIFY COLUMN status {_enum(_STATUSES)} NOT NULL")
        op.execute(f"ALTER TABLE offers MODIFY COLUMN status {_enum(_STATUSES)} NOT NULL")
    op.drop_column("offers", "withdrawal_count")
    op.drop_column("offers", "validity_confirmed_at")
