"""double-blind reviews and invitations

Batch C (business-logic fixes):
- reviews.revealed_at: a review stays sealed from the other side (and from
  ratings) until both sides have reviewed, or 14 days after it was written.
  Reviews already on record were visible, so they are revealed as written;
- notification requirement_invitation: an owner invites a provider it
  completed work with to make an offer on an open requirement.

Revision ID: 0067
Revises: 0066
Create Date: 2026-10-09
"""
import sqlalchemy as sa
from alembic import op

revision = "0067"
down_revision = "0066"
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
    "agreement_terms_confirmed", "agreement_in_force", "agreement_terminated",    "offer_confirmation_requested", "evaluation_started",
]


def _enum(values) -> str:
    return "ENUM(" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.add_column("reviews", sa.Column("revealed_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE reviews SET revealed_at = created_at")
    if op.get_bind().dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES + ['requirement_invitation'])} NOT NULL")


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE type = 'requirement_invitation'")
    if op.get_bind().dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES)} NOT NULL")
    op.drop_column("reviews", "revealed_at")
