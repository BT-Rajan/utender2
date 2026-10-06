"""verification policy scope, final rejection, and review notes

Step 4 of the user journey.

  * document_requirements.applies_to_stakeholder (individual | organization,
    NULL = both) and requires_expiry: an admin's verification policy can now
    target a stakeholder type and demand an expiry date on approval. Existing
    requirements keep applying to everyone (NULL), so nobody's checklist
    changes until an admin narrows one.
  * verification_status gains 'rejected' (a final refusal, distinct from
    'changes_requested') on both profile tables.
  * verification_submitted_at / verification_note on both profile tables:
    when the application was submitted, and the admin's message for an
    application-level decision.
  * notifications.type gains verification_changes_requested and
    verification_rejected (appended, matching the model's order).

Like 0003/0005-0008 this uses MySQL-specific DDL for the ENUM changes.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-06

"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

_PROFILES = ("owner_profiles", "service_provider_profiles")
_STATUSES = ["incomplete", "pending_review", "changes_requested", "approved"]
_NOTIFICATION_TYPES = [
    "document_rejected", "document_approved", "verification_activated", "payment_activated", "payment_failed",
    "payment_override_granted", "payment_override_revoked", "service_provider_suspended", "service_provider_reactivated",
    "owner_verification_activated", "owner_document_rejected", "owner_document_approved", "owner_suspended",
    "owner_reactivated", "document_expiring", "tender_amendment", "drawing_revised", "clarification_asked",
    "clarification_answered", "bid_submitted", "bid_revised", "bid_withdrawn", "deadline_approaching",
    "tender_closed", "evaluation_ready", "award_won", "award_lost", "tender_cancelled", "tender_no_award",
    "project_suspended", "project_reactivated", "offer_suspended", "offer_reactivated",
]
_NEW_NOTIFICATION_TYPES = ["verification_changes_requested", "verification_rejected"]


def _enum(values) -> str:
    return "ENUM(" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.add_column(
        "document_requirements",
        sa.Column("applies_to_stakeholder", sa.Enum("individual", "organization", name="stakeholdertype"), nullable=True),
    )
    op.add_column(
        "document_requirements",
        sa.Column("requires_expiry", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    for table in _PROFILES:
        op.execute(
            f"ALTER TABLE {table} MODIFY COLUMN verification_status {_enum(_STATUSES + ['rejected'])} NOT NULL DEFAULT 'incomplete'"
        )
        op.add_column(table, sa.Column("verification_submitted_at", sa.DateTime(), nullable=True))
        op.add_column(table, sa.Column("verification_note", sa.Text(), nullable=True))
    op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_NOTIFICATION_TYPES + _NEW_NOTIFICATION_TYPES)} NOT NULL")


def downgrade() -> None:
    new = ", ".join(f"'{v}'" for v in _NEW_NOTIFICATION_TYPES)
    op.execute(f"DELETE FROM notifications WHERE type IN ({new})")
    op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_NOTIFICATION_TYPES)} NOT NULL")
    for table in _PROFILES:
        op.drop_column(table, "verification_note")
        op.drop_column(table, "verification_submitted_at")
        # A rejected application goes back to "changes requested", the
        # closest state the older schema can represent.
        op.execute(f"UPDATE {table} SET verification_status = 'changes_requested' WHERE verification_status = 'rejected'")
        op.execute(f"ALTER TABLE {table} MODIFY COLUMN verification_status {_enum(_STATUSES)} NOT NULL DEFAULT 'incomplete'")
    op.drop_column("document_requirements", "requires_expiry")
    op.drop_column("document_requirements", "applies_to_stakeholder")
