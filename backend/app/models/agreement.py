from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import gen_uuid


# Stage 7.3: the agreement governing an awarded requirement. One per award,
# created with it (and backfilled for earlier awards), never re-pointed: the
# parties, the agreed value, the winning offer and the scope version are the
# award record's and are read from it, never copied here -- so an agreement
# can neither drift from nor rewrite the award. It adds only what the award
# doesn't say: where the agreement stands (preparing / active / terminated),
# from when it takes effect, and the parties' own reference for it (their
# contract, work order or purchase order number). The parties agree outside
# U-Tender; the signed papers are attached as AgreementDocument rows.
# Stage 7.11: "completed" -- the owner accepted the whole work; the
# transaction is closed and final (completed_at). "terminated" is the other
# ending: stopped before the work was completed. Neither reopens.
AGREEMENT_STATUSES = ("preparing", "active", "completed", "terminated")


class Agreement(Base):
    __tablename__ = "agreements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    award_id: Mapped[str] = mapped_column(String(36), ForeignKey("award_records.id", ondelete="CASCADE"), nullable=False, unique=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="preparing", server_default="preparing")
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    termination_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Stage 7.5: execution start -- when the work actually began (server
    # time, recorded once), by which side and member, with an optional note.
    # The execution status is derived: not started / in progress / terminated.
    # The planned start is the winning offer's commitment (or the
    # requirement's expected start) and is read from there, never copied.
    work_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    work_started_party: Mapped[str | None] = mapped_column(String(16), nullable=True)
    work_started_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    work_start_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Stage 7.6: set while the work is on hold (server time it was put on
    # hold); cleared when it resumes. The status stays derived from these.
    on_hold_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Stage 7.10: the whole work's completion. The winning provider submits it
    # as complete (only once every deliverable is accepted); the owner side
    # accepts it or returns it for correction. Accepted work is what Stage
    # 7.11's closure builds on. Each step is also an execution-history entry
    # (delivered / accepted / returned with no deliverable).
    completion_status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # submitted / accepted / returned
    completion_submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completion_submitted_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completion_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    completion_decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completion_decided_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completion_decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # Stage 7.11: when it closed
    # Stage 3.11's rule: a change sent from a page showing an older version
    # (another tab, another member) is refused, not silently applied.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


AGREEMENT_DOCUMENT_KINDS = (
    "signed_agreement", "work_order", "purchase_order", "final_quotation", "agreed_scope", "certificate",
    # Stage 7.8: a variation's papers
    "change_order", "revised_agreement", "revised_quotation", "revised_specification", "approval",
    # Stage 7.9: execution evidence
    "progress_photo", "site_report", "delivery_record", "completion_report", "inspection_report", "test_result",
    "other",
)
# Stage 7.9: what shows the work being done or delivered -- as opposed to the
# papers that govern it. Evidence needs the work to have started.
EVIDENCE_KINDS = ("progress_photo", "site_report", "delivery_record", "completion_report", "inspection_report", "test_result")


class AgreementDocument(Base):
    __tablename__ = "agreement_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    agreement_id: Mapped[str] = mapped_column(String(36), ForeignKey("agreements.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # Which party attached it -- "owner" or "provider" -- the side, not the
    # member: any member of that side may remove it while it's being prepared.
    party: Mapped[str] = mapped_column(String(16), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Stage 7.7: evidence for one deliverable of this same agreement, if any.
    milestone_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("milestones.id", ondelete="SET NULL"), nullable=True, index=True)
    # Stage 7.8: a paper of one variation of this same agreement, if any.
    variation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("variations.id", ondelete="SET NULL"), nullable=True, index=True)
    # Stage 7.9: evidence for one progress update of this same agreement, if any.
    # A document belongs to at most one of: a deliverable, a variation, a progress update.
    execution_update_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("execution_updates.id", ondelete="SET NULL"), nullable=True, index=True)
    uploaded_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


# Stage 7.6: what the parties have recorded about the work since it started --
# the start itself (7.5), short progress notes, putting it on hold and
# resuming -- in order, never edited. The parties' own history of the
# execution; the admin audit log records the same events for moderation.
EXECUTION_UPDATE_KINDS = ("started", "progress", "on_hold", "resumed", "delivered", "accepted", "returned")


class ExecutionUpdate(Base):
    __tablename__ = "execution_updates"
    __table_args__ = (UniqueConstraint("agreement_id", "sequence", name="uq_execution_update_sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    agreement_id: Mapped[str] = mapped_column(String(36), ForeignKey("agreements.id", ondelete="CASCADE"), nullable=False, index=True)
    # 1, 2, 3... per agreement, taken under the requirement's lock: the order
    # of events never depends on two rows sharing a second.
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    party: Mapped[str] = mapped_column(String(16), nullable=False)
    recorded_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Stage 7.7: delivered / accepted / returned entries name their deliverable.
    milestone_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("milestones.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


# Stage 7.7: the deliverables of an agreement, where the work naturally has
# them -- none for a simple one-off service. The owner side sets them out
# while the agreement is being prepared (optionally from the requirement's own
# items); once it is in force they are what was agreed and stay as they are.
# The winning provider delivers each; the owner side accepts it or returns it
# for correction: delivered is not accepted.
MILESTONE_STATUSES = ("pending", "delivered", "accepted", "returned")


class Milestone(Base):
    __tablename__ = "milestones"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    agreement_id: Mapped[str] = mapped_column(String(36), ForeignKey("agreements.id", ondelete="CASCADE"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    # The requirement item it delivers, when it comes from one.
    project_item_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("project_items.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending")
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    delivery_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Stage 7.8: added by this agreed variation (not part of the original agreement).
    variation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("variations.id", ondelete="SET NULL"), nullable=True)


# Stage 7.8: an agreed change to the work after the agreement is in force.
# One party proposes it, the other agrees (or rejects it); the proposer may
# withdraw it while it is open. Only one is open at a time. Nothing in the
# award, the requirement or the original agreement is ever rewritten: the
# current agreed state is the original plus the agreed variations, in order --
# each keeps what it changed from (previous_*) and the result it agreed
# (resulting_amount). Termination lapses an open proposal.
VARIATION_STATUSES = ("proposed", "agreed", "rejected", "withdrawn", "lapsed")


class Variation(Base):
    __tablename__ = "variations"
    __table_args__ = (UniqueConstraint("agreement_id", "number", name="uq_variation_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    agreement_id: Mapped[str] = mapped_column(String(36), ForeignKey("agreements.id", ondelete="CASCADE"), nullable=False, index=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)  # V1, V2... per agreement, taken under the lock
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed", server_default="proposed")
    # What changes: the scope, quantities or specification, in words (required).
    description: Mapped[str] = mapped_column(Text, nullable=False)
    value_change: Mapped[Decimal | None] = mapped_column(Numeric(15, 3), nullable=True)  # + or -
    completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # the revised completion
    milestone_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("milestones.id", ondelete="SET NULL"), nullable=True)
    milestone_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # its revised due date
    add_deliverable: Mapped[str | None] = mapped_column(String(200), nullable=True)  # an added deliverable
    proposed_party: Mapped[str] = mapped_column(String(16), nullable=False)
    proposed_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    proposed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    decided_party: Mapped[str | None] = mapped_column(String(16), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Kept when agreed: what it changed from, and the value it agreed.
    previous_amount: Mapped[Decimal | None] = mapped_column(Numeric(15, 3), nullable=True)
    resulting_amount: Mapped[Decimal | None] = mapped_column(Numeric(15, 3), nullable=True)
    previous_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    previous_milestone_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
