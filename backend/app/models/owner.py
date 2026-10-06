from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Text, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import StakeholderType, VerificationStatus


# Mirrors ServiceProviderProfile's shape for the parts that apply to owners too
# (document-backed verification + suspension) — owners have no payment/
# subscription concept, so this is deliberately smaller than
# ServiceProviderProfile rather than a shared base class, to avoid dragging
# payment-gate fields onto a role that was never meant to have them.
class OwnerProfile(Base):
    __tablename__ = "owner_profiles"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, native_enum=True), nullable=False, default=VerificationStatus.incomplete
    )
    # When the current application was last submitted, and the admin's
    # message for an application-level decision (changes requested / rejected).
    verification_submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_suspended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Step 3 stakeholder identity. This profile is the marketplace actor for
    # its side (it owns the verification state, and every project/offer/
    # review points at it); stakeholder_type says whether it represents the
    # person themselves or an organization, and organization_id which one.
    # NULL stakeholder_type = account created, stakeholder not yet established.
    stakeholder_type: Mapped[StakeholderType | None] = mapped_column(Enum(StakeholderType, native_enum=True), nullable=True)
    organization_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    organization = relationship("Organization")
    user = relationship("User", back_populates="owner_profile")

    # THE single source of truth for whether this owner may post/manage
    # projects — mirrors ServiceProviderProfile.is_verified_active. Never check
    # verification_status or is_suspended independently at a call site.
    @property
    def is_verified_active(self) -> bool:
        return self.verification_status == VerificationStatus.approved and not self.is_suspended

    # Human-facing lifecycle status, purely derived — same four
    # document-flow states service providers have, minus the payment states
    # that don't apply to owners.
    @property
    def marketplace_status(self) -> str:
        if self.is_suspended:
            return "suspended"
        if self.verification_status == VerificationStatus.incomplete:
            return "documents_incomplete"
        if self.verification_status == VerificationStatus.pending_review:
            return "submitted_for_review"
        if self.verification_status == VerificationStatus.changes_requested:
            return "changes_requested"
        if self.verification_status == VerificationStatus.rejected:
            return "rejected"
        return "verified_active"
