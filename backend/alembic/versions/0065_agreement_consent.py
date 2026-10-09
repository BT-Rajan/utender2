"""agreement consent and termination party

Batch A (business-logic fixes): the winning provider confirms the
agreement's terms before the owner side can put it in force
(provider_confirmed_at / _by), either party may terminate (terminated_party),
and three notifications tell the other party: terms confirmed, agreement in
force, agreement terminated.

Revision ID: 0065
Revises: 0064
Create Date: 2026-10-09
"""
import sqlalchemy as sa
from alembic import op

revision = "0065"
down_revision = "0064"
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
]
_NEW = ["agreement_terms_confirmed", "agreement_in_force", "agreement_terminated"]


def _enum(values) -> str:
    return "ENUM(" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.add_column("agreements", sa.Column("terminated_party", sa.String(16), nullable=True))
    op.add_column("agreements", sa.Column("provider_confirmed_at", sa.DateTime(), nullable=True))
    op.add_column("agreements", sa.Column("provider_confirmed_by", sa.String(36), nullable=True))
    op.create_foreign_key("fk_agreements_provider_confirmed_by", "agreements", "users", ["provider_confirmed_by"], ["id"], ondelete="SET NULL")
    # Agreements already terminated were terminated by the owner side (the only side that could).
    op.execute("UPDATE agreements SET terminated_party = 'owner' WHERE status = 'terminated'")
    if op.get_bind().dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES + _NEW)} NOT NULL")


def downgrade() -> None:
    bind = op.get_bind()
    op.execute("DELETE FROM notifications WHERE type IN ('agreement_terms_confirmed', 'agreement_in_force', 'agreement_terminated')")
    if bind.dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES)} NOT NULL")
    op.drop_constraint("fk_agreements_provider_confirmed_by", "agreements", type_="foreignkey")
    for column in ("provider_confirmed_by", "provider_confirmed_at", "terminated_party"):
        op.drop_column("agreements", column)
