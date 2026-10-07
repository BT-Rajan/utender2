"""closure follow-ups

Stage 3.16:
  * projects.closure_note: the owner's private note on why a requirement
    ended, readable by the owner side (and admins), never by providers --
    backfilled from the audit trail, where it was recorded until now;
  * notifications.type gains requirement_ended: providers who were told
    about a requirement but hadn't offered hear that it ended early.

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-07

"""
import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
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
    "tender_paused", "tender_resumed",
]
_NEW = ["requirement_ended"]
_ENDINGS = ("project.cancel", "project.no_award", "project.closed_externally")


def _enum(values) -> str:
    return "ENUM(" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.add_column("projects", sa.Column("closure_note", sa.Text(), nullable=True))
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT target_id, reason FROM audit_logs WHERE target_type = 'project' AND reason IS NOT NULL"
            " AND action IN :actions ORDER BY created_at"
        ).bindparams(sa.bindparam("actions", expanding=True)),
        {"actions": list(_ENDINGS)},
    ).fetchall()
    for target_id, reason in rows:  # oldest first: the last ending wins
        bind.execute(sa.text("UPDATE projects SET closure_note = :n WHERE id = :i AND closure_reason IS NOT NULL"), {"n": reason, "i": target_id})
    if bind.dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES + _NEW)} NOT NULL")


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE type = 'requirement_ended'")
    if op.get_bind().dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES)} NOT NULL")
    op.drop_column("projects", "closure_note")
