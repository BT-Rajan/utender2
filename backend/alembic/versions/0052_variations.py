"""variations

Stage 7.8: agreed changes after the agreement is in force (variations),
their papers (agreement_documents.variation_id), deliverables a variation
added (milestones.variation_id), and the variation_updated notification.

Downgrade drops them. It is refused while any variation exists, unless
ALLOW_VARIATION_LOSS=1 is set.

Revision ID: 0052
Revises: 0051
Create Date: 2026-10-08

"""
import os

import sqlalchemy as sa
from alembic import op

revision = "0052"
down_revision = "0051"
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
    "milestone_updated",
]
_NEW = ["variation_updated"]


def _enum(values) -> str:
    return "ENUM(" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.create_table(
        "variations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agreement_id", sa.String(36), sa.ForeignKey("agreements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("value_change", sa.Numeric(15, 3), nullable=True),
        sa.Column("completion_date", sa.Date(), nullable=True),
        sa.Column("milestone_id", sa.String(36), sa.ForeignKey("milestones.id", ondelete="SET NULL"), nullable=True),
        sa.Column("milestone_due_date", sa.Date(), nullable=True),
        sa.Column("add_deliverable", sa.String(200), nullable=True),
        sa.Column("proposed_party", sa.String(16), nullable=False),
        sa.Column("proposed_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("proposed_at", sa.DateTime(), nullable=False),
        sa.Column("decided_party", sa.String(16), nullable=True),
        sa.Column("decided_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("previous_amount", sa.Numeric(15, 3), nullable=True),
        sa.Column("resulting_amount", sa.Numeric(15, 3), nullable=True),
        sa.Column("previous_completion_date", sa.Date(), nullable=True),
        sa.Column("previous_milestone_due_date", sa.Date(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("agreement_id", "number", name="uq_variation_number"),
    )
    op.create_index("ix_variations_agreement_id", "variations", ["agreement_id"])
    op.add_column("agreement_documents", sa.Column("variation_id", sa.String(36), nullable=True))
    op.create_index("ix_agreement_documents_variation_id", "agreement_documents", ["variation_id"])
    op.create_foreign_key("fk_agreement_documents_variation", "agreement_documents", "variations", ["variation_id"], ["id"], ondelete="SET NULL")
    op.add_column("milestones", sa.Column("variation_id", sa.String(36), nullable=True))
    op.create_foreign_key("fk_milestones_variation", "milestones", "variations", ["variation_id"], ["id"], ondelete="SET NULL")
    if op.get_bind().dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES + _NEW)} NOT NULL")


def downgrade() -> None:
    bind = op.get_bind()
    held = bind.execute(sa.text("SELECT COUNT(*) FROM variations")).scalar()
    if held and os.environ.get("ALLOW_VARIATION_LOSS") != "1":
        raise RuntimeError(f"{held} variation(s) would be lost by this downgrade. Set ALLOW_VARIATION_LOSS=1 to proceed anyway.")
    op.execute("DELETE FROM notifications WHERE type = 'variation_updated'")
    if bind.dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES)} NOT NULL")
    op.drop_constraint("fk_milestones_variation", "milestones", type_="foreignkey")
    op.drop_column("milestones", "variation_id")
    op.drop_constraint("fk_agreement_documents_variation", "agreement_documents", type_="foreignkey")
    op.drop_index("ix_agreement_documents_variation_id", table_name="agreement_documents")
    op.drop_column("agreement_documents", "variation_id")
    op.drop_table("variations")
