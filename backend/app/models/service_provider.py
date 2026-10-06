from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import StakeholderType, SubscriptionStatus, VerificationStatus


class ServiceProviderProfile(Base):
    __tablename__ = "service_provider_profiles"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    license_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    primary_trade: Mapped[str | None] = mapped_column(String(100), nullable=True)
    service_area: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, native_enum=True), nullable=False, default=VerificationStatus.incomplete
    )
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
    avg_rating: Mapped[Decimal] = mapped_column(Numeric(2, 1), default=Decimal("0"))
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subscription_status: Mapped[SubscriptionStatus | None] = mapped_column(
        Enum(SubscriptionStatus, native_enum=True), nullable=True
    )
    subscription_current_period_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Denormalized "is there currently an active admin payment override"
    # flag — kept in sync by the payment_overrides service whenever a
    # PaymentOverride row is created or revoked. Reading this is a hot path
    # (every tender-feed and bid-submit request), so it's a column rather
    # than a per-request join; the PaymentOverride table is the audited
    # system of record for who/why/when.
    payment_override_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    organization = relationship("Organization")
    user = relationship("User", back_populates="service_provider_profile")

    @property
    def is_payment_active(self) -> bool:
        return self.subscription_status in (SubscriptionStatus.active, SubscriptionStatus.trialing)

    # Kept for backward compatibility with existing call sites written
    # before the payment-gate/verification-gate split; means the same
    # thing as is_payment_active.
    @property
    def is_subscribed(self) -> bool:
        return self.is_payment_active

    # THE single source of truth for marketplace activation (spec §8-11,
    # decision D-002/D-003, checklist P0 "docs approved but payment
    # absent"). Every route that gates tender visibility, drawings, or
    # bidding must check this — never verification_status alone, and never
    # subscription_status alone.
    @property
    def is_verified_active(self) -> bool:
        if self.is_suspended:
            return False
        if self.verification_status != VerificationStatus.approved:
            return False
        return self.is_payment_active or self.payment_override_active

    # Human-facing lifecycle status (spec §2.13). Purely derived — never
    # stored — so it can never drift out of sync with the fields it's
    # computed from.
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
        if self.payment_override_active:
            return "verified_active"
        if self.is_payment_active:
            return "verified_active"
        if self.subscription_status in (SubscriptionStatus.past_due, SubscriptionStatus.failed):
            return "payment_restricted"
        return "payment_required"
