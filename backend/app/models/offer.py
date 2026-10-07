from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import gen_uuid
from app.models.enums import OfferStatus


class Offer(Base):
    __tablename__ = "offers"
    # One offer per provider -- and per organization (NULLs, individuals, are
    # distinct to the database, so this only binds organizations).
    __table_args__ = (
        UniqueConstraint("project_id", "service_provider_id", name="uq_project_service_provider"),
        UniqueConstraint("project_id", "organization_id", name="uq_project_organization"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service_provider_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("service_provider_profiles.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The organization this was done for (services.team); NULL = an individual's.
    organization_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # KWD: 3 decimals (fils). NULL only while a draft (Stage 5.2): every
    # submitted, approved, rejected or withdrawn offer carries its amount.
    amount: Mapped[Decimal | None] = mapped_column(Numeric(15, 3), nullable=True)
    # Stage 3.15: the requirement's material_revision this offer was made or
    # last confirmed against. Lower than the requirement's = made before a
    # material change: the provider is asked to review and confirm or revise.
    based_on_material_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    timeline_estimate: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Stage 5.5: the provider's execution commitment, answering the owner's
    # expected timing (Stage 3.7) in the same terms -- a start date, and a
    # completion date or a duration in days. timeline_estimate stays the
    # free-text "completion period" (Stage 3.8) for anything else to say.
    proposed_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    proposed_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    proposed_duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Stage 3.8 response content. item_prices: [{"item_id", "rate", "line_total"}]
    # when the requirement is priced per item (amount is then their sum);
    # assumptions: the provider's clarifications/assumptions/exclusions;
    # declarations_accepted: the requirement's declarations as worded when
    # the provider accepted them.
    item_prices: Mapped[list | None] = mapped_column(JSON, nullable=True)
    assumptions: Mapped[str | None] = mapped_column(Text, nullable=True)
    declarations_accepted: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[OfferStatus] = mapped_column(
        Enum(OfferStatus, native_enum=True), nullable=False, default=OfferStatus.submitted
    )
    # Admin moderation flag, independent of `status` — a suspended offer is
    # hidden from the owner's evaluation view and cannot be awarded, but
    # keeps its real submitted/approved/rejected/withdrawn status intact so
    # un-suspending restores exactly what was there before.
    is_suspended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # This row is always the CURRENT bid. Every edit also appends an
    # OfferRevision snapshot of the pre-edit values and bumps this counter
    # (spec §29, D-009) — old values are never lost, just superseded.
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Stage 5.3: bumped by every save of the draft, so a save from a page
    # showing an older draft (another tab, another member) is refused
    # instead of overwriting newer work (If-Match, as for requirement drafts).
    draft_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Stage 5.13: the supporting documents as they stood when this version was
    # submitted -- [{"label", "file_name", "file_path"}]. Documents can be
    # replaced while preparing a revision; what the owner receives is what was
    # submitted, until the next submission.
    submitted_documents: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Stage 5.11: when it was first put forward (submitted); NULL while a draft.
    # created_at is when the draft was started.
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Stage 5.2: the people who started it and last changed it (an
    # organization's members share one offer).
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    service_provider_profile = relationship("ServiceProviderProfile")


def tendered():
    """SQL condition: offers actually put forward -- every state but an
    unsubmitted draft (Stage 5.2). Owners, competitors, counts, admins and
    lifecycle decisions only ever see these."""
    return Offer.status != OfferStatus.draft


# Immutable log of every prior state of an Offer, written just before the
# current row is overwritten. revision_number matches what Offer.revision
# was AT THAT SNAPSHOT (so revision 1's row here is the bid as originally
# submitted, before the edit that created revision 2).
class OfferRevision(Base):
    __tablename__ = "offer_revisions"
    __table_args__ = (UniqueConstraint("offer_id", "revision_number", name="uq_offer_revision"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    offer_id: Mapped[str] = mapped_column(String(36), ForeignKey("offers.id", ondelete="CASCADE"), nullable=False, index=True)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 3), nullable=False)  # KWD: 3 decimals (fils)
    timeline_estimate: Mapped[str | None] = mapped_column(String(255), nullable=True)
    proposed_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    proposed_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    proposed_duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_prices: Mapped[list | None] = mapped_column(JSON, nullable=True)
    assumptions: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[OfferStatus] = mapped_column(Enum(OfferStatus, native_enum=True), nullable=False)
    # Stage 3.17: the requirement version this earlier submission was made against.
    based_on_material_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Stage 5.13: the rest of what that version said, and when and by whom it
    # was put forward (the offer's last change before it was superseded).
    declarations_accepted: Mapped[list | None] = mapped_column(JSON, nullable=True)
    documents: Mapped[list | None] = mapped_column(JSON, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    submitted_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# Stage 3.8: a file a provider submits with their response (method statement,
# programme, data sheets...), against one of the documents the requirement
# asks for (label). Keyed like the offer itself -- one requirement, one
# provider. Re-uploading the same label replaces it until bidding closes.
# Stage 5.6: it belongs to the side's offer (offer_id: the draft Participate
# started, or the offer it became), and records the requirement version it
# was supplied against and who supplied it.
class OfferDocument(Base):
    __tablename__ = "offer_documents"
    __table_args__ = (
        UniqueConstraint("project_id", "service_provider_id", "label", name="uq_offer_document_label"),
        UniqueConstraint("project_id", "organization_id", "label", name="uq_offer_document_org_label"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service_provider_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("service_provider_profiles.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The organization this was done for (services.team); NULL = an individual's.
    organization_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    offer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("offers.id", ondelete="CASCADE"), nullable=True, index=True)
    material_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    uploaded_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
