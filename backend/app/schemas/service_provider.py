from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import OfferStatus, ProjectStatus, SubscriptionStatus, VerificationStatus


class ServiceProviderProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    company_name: str
    license_number: str | None
    primary_trade: str | None
    service_area: str | None
    verification_status: VerificationStatus
    is_suspended: bool
    avg_rating: Decimal
    review_count: int
    subscription_status: SubscriptionStatus | None
    subscription_current_period_end: datetime | None
    payment_override_active: bool
    # Derived, never stored — spec §2.13's human-facing lifecycle status,
    # one of: documents_incomplete, submitted_for_review, changes_requested,
    # payment_required, payment_restricted, verified_active, suspended.
    marketplace_status: str
    created_at: datetime
    email: str | None = None


class ServiceProviderProfileUpdate(BaseModel):
    company_name: str
    license_number: str | None = None
    primary_trade: str | None = None
    service_area: str | None = None


class SubmitForReview(BaseModel):
    company_name: str
    license_number: str | None = None


class MyBidOut(BaseModel):
    project_id: str
    project_title: str
    project_address: str
    project_status: ProjectStatus
    bid_deadline: datetime
    offer_id: str
    amount: Decimal
    offer_status: OfferStatus
    revision: int
    updated_at: datetime
