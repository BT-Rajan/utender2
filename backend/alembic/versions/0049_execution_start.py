"""execution start

Stage 7.5: when the awarded work actually started, on the award's agreement
(work_started_at / _party / _by / work_start_note), and the work_started
notification to the other party.

Downgrade drops them. It is refused while any agreement records a start,
unless ALLOW_EXECUTION_LOSS=1 is set.

Revision ID: 0049
Revises: 0048
Create Date: 2026-10-08

"""
import os

import sqlalchemy as sa
from alembic import op

revision = "0049"
down_revision = "0048"
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
    "offer_clarification_requested", "offer_clarification_answered",
]
_NEW = ["work_started"]


def _enum(values) -> str:
    return "ENUM(" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.add_column("agreements", sa.Column("work_started_at", sa.DateTime(), nullable=True))
    op.add_column("agreements", sa.Column("work_started_party", sa.String(16), nullable=True))
    op.add_column("agreements", sa.Column("work_started_by", sa.String(36), nullable=True))
    op.add_column("agreements", sa.Column("work_start_note", sa.Text(), nullable=True))
    op.create_foreign_key("fk_agreements_work_started_by", "agreements", "users", ["work_started_by"], ["id"], ondelete="SET NULL")
    if op.get_bind().dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES + _NEW)} NOT NULL")


def downgrade() -> None:
    bind = op.get_bind()
    held = bind.execute(sa.text("SELECT COUNT(*) FROM agreements WHERE work_started_at IS NOT NULL")).scalar()
    if held and os.environ.get("ALLOW_EXECUTION_LOSS") != "1":
        raise RuntimeError(f"{held} recorded execution start(s) would be lost by this downgrade. Set ALLOW_EXECUTION_LOSS=1 to proceed anyway.")
    op.execute("DELETE FROM notifications WHERE type = 'work_started'")
    if bind.dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES)} NOT NULL")
    op.drop_constraint("fk_agreements_work_started_by", "agreements", type_="foreignkey")
    for column in ("work_start_note", "work_started_by", "work_started_party", "work_started_at"):
        op.drop_column("agreements", column)
