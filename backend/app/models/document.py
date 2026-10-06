from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import gen_uuid
from app.models.enums import DocumentStatus, StakeholderType, UserRole


class DocumentRequirement(Base):
    __tablename__ = "document_requirements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Which self-registering role this requirement's checklist applies to
    # (owner or service provider — reuses UserRole rather than a new two-value
    # enum since the values already line up; 'admin' is never a valid
    # value here, enforced at the API layer, not the column type).
    applies_to: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=True), nullable=False, default=UserRole.service_provider
    )
    # Versioning (spec §48): when this requirement took effect. Combined
    # with is_active (retire without deleting — see removeRequirement),
    # this is enough to answer "was this requirement in force on date X"
    # for audit purposes without a full historical-snapshot table. Adding
    # a requirement never retroactively blocks an already-approved
    # service provider — nothing re-checks past approvals against new rows.
    # Which stakeholders of that role it applies to: individuals, organizations,
    # or (NULL) both. Selected in exactly one place,
    # services.verification.applicable_requirements -- a future country (or
    # other) scope belongs there too.
    applies_to_stakeholder: Mapped[StakeholderType | None] = mapped_column(Enum(StakeholderType, native_enum=True), nullable=True)
    # The reviewing admin must record an expiry date when approving this
    # document (e.g. a licence that lapses).
    requires_expiry: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ServiceProviderDocument(Base):
    __tablename__ = "service_provider_documents"
    __table_args__ = (UniqueConstraint("service_provider_id", "requirement_id", name="uq_service_provider_requirement"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    service_provider_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("service_provider_profiles.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    requirement_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("document_requirements.id", ondelete="CASCADE"), nullable=False
    )
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, native_enum=True), nullable=False, default=DocumentStatus.not_submitted
    )
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    requirement = relationship("DocumentRequirement")


class OwnerDocument(Base):
    """Mirrors ServiceProviderDocument exactly, for the owner-side verification
    checklist (e.g. civil ID, land ownership proof) — kept as a separate
    table rather than a shared one so an owner's and a service provider's
    documents never collide even if a name coincidentally matched, and so
    each side's row count/growth is independent."""

    __tablename__ = "owner_documents"
    __table_args__ = (UniqueConstraint("owner_id", "requirement_id", name="uq_owner_requirement"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("owner_profiles.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    requirement_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("document_requirements.id", ondelete="CASCADE"), nullable=False
    )
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, native_enum=True), nullable=False, default=DocumentStatus.not_submitted
    )
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    requirement = relationship("DocumentRequirement")
