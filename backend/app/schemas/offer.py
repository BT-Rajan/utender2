from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import OfferStatus


class OfferItemPrice(BaseModel):
    item_id: str
    rate: Decimal = Field(ge=0, decimal_places=3)


class OfferCreate(BaseModel):
    # The total. When the requirement is priced per item it's computed from
    # item_prices instead (any value sent is ignored).
    amount: Decimal | None = Field(default=None, decimal_places=3)
    item_prices: list[OfferItemPrice] | None = Field(default=None, max_length=300)
    assumptions: str | None = Field(default=None, max_length=10_000)
    # The declarations the provider accepts, as worded on the requirement.
    accepted_declarations: list[str] = Field(default_factory=list, max_length=10)
    # Bounds mirror the columns (String(255) / TEXT): longer input would be a
    # database error (a 500 under MySQL strict mode), so it is refused as
    # invalid input instead.
    timeline_estimate: str | None = Field(default=None, max_length=255)
    message: str | None = Field(default=None, max_length=10_000)


class OfferCommercialDraft(BaseModel):
    """Stage 5.3: the commercial part of an offer draft, saved without
    submitting. Either may be incomplete while it is a draft: a total not yet
    entered, or rates for only some items. Totals are always the server's."""

    amount: Decimal | None = Field(default=None, decimal_places=3)
    item_prices: list[OfferItemPrice] | None = Field(default=None, max_length=300)


class OfferTechnicalDraft(BaseModel):
    """Stage 5.4: the technical part of an offer draft -- how the provider
    will do the work and how it meets the requirement's scope,
    specifications and instructions (the requirement's "technical approach /
    method", Stage 3.8) -- saved without submitting. May be empty while a
    draft; whether it is required is checked on submission."""

    message: str | None = Field(default=None, max_length=10_000)


class OfferAssumptionsDraft(BaseModel):
    """Stage 5.7: the provider's assumptions, exclusions, qualifications and
    offer-specific clarifications (offers.assumptions, Stage 3.8) -- the
    conditions attached to their own offer, kept as written for the owner
    to weigh. Not a question about the requirement (those are Stage 4.7
    clarifications). May be empty while a draft."""

    assumptions: str | None = Field(default=None, max_length=10_000)


class OfferTimingDraft(BaseModel):
    """Stage 5.5: when the provider commits to start and finish, in the terms
    the requirement uses (Stage 3.7): a start date, and a completion date or a
    duration in days; plus the free-text completion period (Stage 3.8).
    Any may be empty while a draft."""

    proposed_start_date: date | None = None
    proposed_completion_date: date | None = None
    proposed_duration_days: int | None = None
    timeline_estimate: str | None = Field(default=None, max_length=255)


class OfferDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    label: str
    file_name: str
    uploaded_at: datetime
    url: str | None = None
    # Stage 5.6: the requirement version it was supplied against.
    material_revision: int = 0


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
    proposed_start_date: date | None = None
    proposed_completion_date: date | None = None
    proposed_duration_days: int | None = None
    # Stage 5.5: where the commitment differs from the owner's expected timing
    # (starts_later | finishes_later | takes_longer), against the requirement
    # as it now is. Flagged, never changed.
    timing_conflicts: list[str] = []
    message: str | None
    item_prices: list[dict] | None = None
    assumptions: str | None = None
    declarations_accepted: list[str] | None = None
    documents: list[OfferDocumentOut] = []
    status: OfferStatus
    is_suspended: bool = False
    revision: int = 1
    # Stage 3.15: the requirement's material revision this offer was made or
    # last confirmed against (lower than the requirement's = before a change).
    based_on_material_revision: int = 0
    draft_version: int = 0  # Stage 5.3: send back as If-Match when saving the draft
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
    proposed_start_date: date | None = None
    proposed_completion_date: date | None = None
    proposed_duration_days: int | None = None
    message: str | None
    item_prices: list[dict] | None = None
    assumptions: str | None = None
    status: OfferStatus
    based_on_material_revision: int = 0  # Stage 3.17: the requirement version it was made against
    recorded_at: datetime
