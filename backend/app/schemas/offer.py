from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import OfferStatus
from app.schemas.common import UTCDateTime
from app.schemas.project import ProjectItemOut


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
    # Stage 5.13: a revision can change the start/completion commitment too.
    # Applied only when sent (an older client's revision keeps what's stored).
    proposed_start_date: date | None = None
    proposed_completion_date: date | None = None
    proposed_duration_days: int | None = None


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


class OfferDraftSave(BaseModel):
    """Stage 5.10: the whole offer form saved in one step -- every part the
    section saves (5.3-5.8) take, validated by the same rules, applied
    together or not at all. Anything may be empty while a draft."""

    amount: Decimal | None = Field(default=None, decimal_places=3)
    item_prices: list[OfferItemPrice] | None = Field(default=None, max_length=300)
    message: str | None = Field(default=None, max_length=10_000)
    assumptions: str | None = Field(default=None, max_length=10_000)
    accepted_declarations: list[str] = Field(default_factory=list, max_length=10)
    proposed_start_date: date | None = None
    proposed_completion_date: date | None = None
    proposed_duration_days: int | None = None
    timeline_estimate: str | None = Field(default=None, max_length=255)


class OfferDeclarationsDraft(BaseModel):
    """Stage 5.8: the requirement's declarations the provider accepts, as
    worded on the requirement, saved on the draft so the quality gate can see
    them. (Submission still takes them with the offer, as before.)"""

    accepted_declarations: list[str] = Field(default_factory=list, max_length=10)


class ReadinessIssue(BaseModel):
    """One thing standing between the draft and submission: the part of the
    offer (or of the provider's standing) it concerns, and what to do."""

    section: str  # requirement | account | eligibility | price | technical | timing | documents | declarations | offer
    message: str


class OfferReadiness(BaseModel):
    """Stage 5.8: the quality gate -- is this offer complete and valid enough
    to submit, against the requirement as it is now? Not an evaluation:
    nothing here says whether the offer is good."""

    ready: bool
    issues: list[ReadinessIssue] = []


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
    submitted_at: UTCDateTime | None = None  # Stage 5.11: when first submitted; None while a draft
    created_at: UTCDateTime  # Stage 5.10: explicit UTC instants, like every other time sent
    updated_at: UTCDateTime
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
    # Stage 5.13: what else that version said, and when/by whom it was submitted.
    declarations_accepted: list[str] | None = None
    documents: list[dict] = []  # [{"label", "file_name", "url"?}] -- never a storage path
    submitted_at: UTCDateTime | None = None
    submitted_by: str | None = None
    recorded_at: UTCDateTime

    @field_validator("documents", mode="before")
    @classmethod
    def _names_only(cls, value):
        return [{k: d.get(k) for k in ("label", "file_name", "url") if d.get(k) is not None} for d in value or []]


class PreviewRequirement(BaseModel):
    """Stage 5.9: enough of the requirement, as it is now, for the provider to
    check the offer is for the right opportunity and version -- not the whole
    requirement."""

    id: str
    title: str
    trade: str | None
    governorate: str | None
    area: str | None
    description: str | None
    pricing_basis: str
    currency: str
    tender_type: str
    bid_deadline: UTCDateTime
    expected_start_date: date | None
    expected_completion_date: date | None
    expected_duration_days: int | None
    material_revision: int  # the current version
    amendment_number: int | None  # the latest amendment, if any
    items: list[ProjectItemOut] = []
    declarations: list[str] = []
    requested_documents: list[dict] = []  # [{"name", "required"}]


class OfferPreviewOut(BaseModel):
    """Stage 5.9: the provider's offer exactly as stored -- what submission
    would send -- with who it is from, the requirement it answers (as it is
    now), and the quality gate's verdict (Stage 5.8). Built on every request
    from the stored offer; there is no separate preview copy."""

    requirement: PreviewRequirement
    provider_name: str | None
    offer: OfferOut
    readiness: OfferReadiness
    on_current_version: bool


class OwnerOfferOut(BaseModel):
    """Stage 6.4: one offer as its requirement's owner reviews it -- exactly as
    submitted (the stored record; nothing recalculated), from whom, and the
    requirement it answers: as it is now, and which version the offer was
    made against (on_current_version False: an earlier one)."""

    requirement: PreviewRequirement
    provider_name: str | None
    offer: OfferOut
    on_current_version: bool


class OfferComparisonOut(BaseModel):
    """Stage 6.6: the owner's chosen offers on one requirement, side by side --
    each exactly as stored, in the order chosen (no ranking), beside the
    requirement as it is now. `unavailable`: ids asked for that aren't
    offers the owner may review on this requirement now (withdrawn,
    suspended, another requirement's...) -- left out, never shown."""

    requirement: PreviewRequirement
    offers: list[OfferOut]
    unavailable: list[str] = []
