from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
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
AGREEMENT_STATUSES = ("preparing", "active", "terminated")


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
    # Stage 3.11's rule: a change sent from a page showing an older version
    # (another tab, another member) is refused, not silently applied.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


AGREEMENT_DOCUMENT_KINDS = ("signed_agreement", "work_order", "purchase_order", "final_quotation", "agreed_scope", "certificate", "other")


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
