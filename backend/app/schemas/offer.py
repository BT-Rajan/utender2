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
    # contractor_id, amount, message, and every contractor_* field below are
    # redacted (set to None) whenever this offer is being viewed by the
    # project's owner on a sealed tender that's still open (spec §19-21,
    # D-001) — see the `sealed` flag. A contractor's own bid, and any bid
    # once the tender is no longer open, is always shown in full.
    contractor_id: str | None
    amount: Decimal | None
    timeline_estimate: str | None
    message: str | None
    status: OfferStatus
    is_suspended: bool = False
    revision: int = 1
    created_at: datetime
    updated_at: datetime
    contractor_company_name: str | None = None
    contractor_avg_rating: Decimal | None = None
    contractor_review_count: int | None = None
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
