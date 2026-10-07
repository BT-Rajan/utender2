"""offer clarifications

Stage 6.10: the owner's side may ask a provider to clarify a submitted offer
during evaluation, through the existing clarifications record.
  * clarifications.offer_id: the offer asked about (NULL: a Stage 4.7
    requirement question from a provider);
  * clarifications.offer_revision: the version of the offer it was about;
  * clarifications.asked_by: who on the owner's side asked;
  * notifications.type gains offer_clarification_requested (to the
    provider's side) and offer_clarification_answered (to the owner's side).

Downgrade removes offer clarifications (questions and answers). It is
refused while any exist, unless ALLOW_CLARIFICATION_LOSS=1 is set.

Revision ID: 0045
Revises: 0044
Create Date: 2026-10-07

"""
import os

import sqlalchemy as sa
from alembic import op

revision = "0045"
down_revision = "0044"
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
]
_NEW = ["offer_clarification_requested", "offer_clarification_answered"]


def _enum(values) -> str:
    return "ENUM(" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.add_column("clarifications", sa.Column("offer_id", sa.String(36), nullable=True))
    op.add_column("clarifications", sa.Column("offer_revision", sa.Integer(), nullable=True))
    op.add_column("clarifications", sa.Column("asked_by", sa.String(36), nullable=True))
    op.create_index("ix_clarifications_offer_id", "clarifications", ["offer_id"])
    op.create_foreign_key("fk_clarifications_offer", "clarifications", "offers", ["offer_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_clarifications_asked_by", "clarifications", "users", ["asked_by"], ["id"], ondelete="SET NULL")
    if op.get_bind().dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES + _NEW)} NOT NULL")


def downgrade() -> None:
    bind = op.get_bind()
    held = bind.execute(sa.text("SELECT COUNT(*) FROM clarifications WHERE offer_id IS NOT NULL")).scalar()
    if held and os.environ.get("ALLOW_CLARIFICATION_LOSS") != "1":
        raise RuntimeError(
            f"{held} offer clarification(s) would be deleted by this downgrade. "
            "Set ALLOW_CLARIFICATION_LOSS=1 to proceed anyway."
        )
    op.execute("DELETE FROM clarifications WHERE offer_id IS NOT NULL")
    op.execute("DELETE FROM notifications WHERE type IN ('offer_clarification_requested', 'offer_clarification_answered')")
    if bind.dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES)} NOT NULL")
    op.drop_constraint("fk_clarifications_asked_by", "clarifications", type_="foreignkey")
    op.drop_constraint("fk_clarifications_offer", "clarifications", type_="foreignkey")
    op.drop_index("ix_clarifications_offer_id", table_name="clarifications")
    op.drop_column("clarifications", "asked_by")
    op.drop_column("clarifications", "offer_revision")
    op.drop_column("clarifications", "offer_id")
