from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
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
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 3), nullable=False)  # KWD: 3 decimals (fils)
    # Stage 3.15: the requirement's material_revision this offer was made or
    # last confirmed against. Lower than the requirement's = made before a
    # material change: the provider is asked to review and confirm or revise.
    based_on_material_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    timeline_estimate: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    service_provider_profile = relationship("ServiceProviderProfile")


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
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_prices: Mapped[list | None] = mapped_column(JSON, nullable=True)
    assumptions: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[OfferStatus] = mapped_column(Enum(OfferStatus, native_enum=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# Stage 3.8: a file a provider submits with their response (method statement,
# programme, data sheets...), against one of the documents the requirement
# asks for (label). Keyed like the offer itself -- one requirement, one
# provider -- so it can be attached before the offer is first submitted.
# Re-uploading the same label replaces it until bidding closes.
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
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
