"""clarification integrity

Stage 4.7:
  * clarifications.answered_by: who on the owner's side answered;
  * clarifications.amendment_id: the amendment an answer came with, when the
    clarification changed the requirement itself;
  * notifications.type gains clarification_shared: providers involved in a
    requirement hear when an answer is published for all of them.

Revision ID: 0034
Revises: 0033
Create Date: 2026-10-07

"""
import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
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
    "tender_paused", "tender_resumed", "requirement_ended",
]
_NEW = ["clarification_shared"]


def _enum(values) -> str:
    return "ENUM(" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.add_column("clarifications", sa.Column("answered_by", sa.String(36), nullable=True))
    op.add_column("clarifications", sa.Column("amendment_id", sa.String(36), nullable=True))
    op.create_foreign_key("fk_clarifications_answered_by", "clarifications", "users", ["answered_by"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_clarifications_amendment", "clarifications", "project_amendments", ["amendment_id"], ["id"], ondelete="SET NULL")
    if op.get_bind().dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES + _NEW)} NOT NULL")


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE type = 'clarification_shared'")
    if op.get_bind().dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES)} NOT NULL")
    op.drop_constraint("fk_clarifications_amendment", "clarifications", type_="foreignkey")
    op.drop_constraint("fk_clarifications_answered_by", "clarifications", type_="foreignkey")
    op.drop_column("clarifications", "amendment_id")
    op.drop_column("clarifications", "answered_by")
