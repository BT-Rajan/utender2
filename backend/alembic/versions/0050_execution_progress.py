"""execution progress

Stage 7.6: the work's execution history the parties record after it starts
(execution_updates: started, progress notes, on hold, resumed), whether it is
on hold now (agreements.on_hold_at), and the execution_updated notification.
Each recorded start (7.5) becomes the history's first entry.

Downgrade drops them. It is refused while any history beyond those starts
exists or any work is on hold, unless ALLOW_EXECUTION_HISTORY_LOSS=1 is set.

Revision ID: 0050
Revises: 0049
Create Date: 2026-10-08

"""
import os
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0050"
down_revision = "0049"
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
    "offer_clarification_requested", "offer_clarification_answered", "work_started",
]
_NEW = ["execution_updated"]


def _enum(values) -> str:
    return "ENUM(" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.add_column("agreements", sa.Column("on_hold_at", sa.DateTime(), nullable=True))
    op.create_table(
        "execution_updates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agreement_id", sa.String(36), sa.ForeignKey("agreements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("party", sa.String(16), nullable=False),
        sa.Column("recorded_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("agreement_id", "sequence", name="uq_execution_update_sequence"),
    )
    op.create_index("ix_execution_updates_agreement_id", "execution_updates", ["agreement_id"])
    bind = op.get_bind()
    started = bind.execute(sa.text(
        "SELECT id, work_started_party, work_started_by, work_start_note, work_started_at FROM agreements WHERE work_started_at IS NOT NULL"
    )).fetchall()
    for agreement_id, party, by, note, at in started:
        bind.execute(
            sa.text("INSERT INTO execution_updates (id, agreement_id, sequence, kind, party, recorded_by, note, created_at)"
                    " VALUES (:id, :a, 1, 'started', :p, :by, :note, :at)"),
            {"id": str(uuid.uuid4()), "a": agreement_id, "p": party or "owner", "by": by, "note": note, "at": at},
        )
    if bind.dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES + _NEW)} NOT NULL")


def downgrade() -> None:
    bind = op.get_bind()
    held = bind.execute(sa.text(
        "SELECT (SELECT COUNT(*) FROM execution_updates WHERE kind <> 'started') + (SELECT COUNT(*) FROM agreements WHERE on_hold_at IS NOT NULL)"
    )).scalar()
    if held and os.environ.get("ALLOW_EXECUTION_HISTORY_LOSS") != "1":
        raise RuntimeError(f"{held} execution update(s) or hold(s) would be lost by this downgrade. Set ALLOW_EXECUTION_HISTORY_LOSS=1 to proceed anyway.")
    op.execute("DELETE FROM notifications WHERE type = 'execution_updated'")
    if bind.dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES)} NOT NULL")
    op.drop_table("execution_updates")
    op.drop_column("agreements", "on_hold_at")
