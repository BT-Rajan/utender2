from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import OfferStatus


class OfferCreate(BaseModel):
    amount: Decimal
    # Bounds mirror the columns (String(255) / TEXT): longer input would be a
    # database error (a 500 under MySQL strict mode), so it is refused as
    # invalid input instead.
    timeline_estimate: str | None = Field(default=None, max_length=255)
    message: str | None = Field(default=None, max_length=10_000)


class OfferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    # service_provider_id, amount, message, and every service_provider_* field below are
    # redacted (set to None) whenever this offer is being viewed by the
    # project's owner on a sealed tender that's still open (spec §19-21,
    # D-001) — see the `sealed` flag. A service provider's own bid, and any bid
    # once the tender is no longer open, is always shown in full.
    service_provider_id: str | None
    amount: Decimal | None
    timeline_estimate: str | None
    message: str | None
    status: OfferStatus
    is_suspended: bool = False
    revision: int = 1
    created_at: datetime
    updated_at: datetime
    service_provider_company_name: str | None = None
    service_provider_avg_rating: Decimal | None = None
    service_provider_review_count: int | None = None
    sealed: bool = False


class OfferRevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    offer_id: str
    revision_number: int
    amount: Decimal
    timeline_estimate: str | None
    message: str | None
    status: OfferStatus
    recorded_at: datetime
