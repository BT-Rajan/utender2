from datetime import date, datetime
from decimal import Decimal

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import PricingBasis, ProjectStatus, TenderType
from app.schemas.common import UTCDateTime


class ProjectCreate(BaseModel):
    title: str
    address: str
    description: str | None = None
    trade: str | None = None
    bid_deadline: datetime
    tender_type: TenderType = TenderType.owner_visible
    # Only these two are valid at creation — every other lifecycle state is
    # reached later through an explicit owner action, never chosen upfront.
    status: ProjectStatus = ProjectStatus.open


class DrawingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    file_name: str
    uploaded_at: datetime
    revision: int
    is_current: bool
    category: str = "drawing"
    is_required: bool = True
    url: str | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    title: str
    # None in the service provider feed: the exact address is shown only on
    # the full requirement (see _can_view_project). Listings use governorate/area.
    address: str | None
    governorate: str | None = None
    area: str | None = None
    description: str | None
    trade: str | None
    # The one authoritative response deadline (enforced server-side by
    # tender_lifecycle.bidding_is_open). Sent as UTC ("...Z").
    bid_deadline: UTCDateTime
    # Stage 3.7: when the owner expects the work to happen -- distinct from
    # the response deadline above. All optional.
    expected_start_date: date | None = None
    expected_completion_date: date | None = None
    expected_duration_days: int | None = None
    status: ProjectStatus
    tender_type: TenderType
    tender_type_locked: bool
    is_suspended: bool = False
    created_at: datetime
    offer_count: int = 0
    my_offer_status: str | None = None  # only populated on the service provider feed


class ProjectItemIn(BaseModel):
    description: str = Field(max_length=500)
    quantity: Decimal | None = Field(default=None, ge=0, le=Decimal("99999999999"), decimal_places=3)
    unit: str | None = Field(default=None, max_length=30)
    specification: str | None = Field(default=None, max_length=4000)


class ProjectItemsUpdate(BaseModel):
    pricing_basis: PricingBasis
    items: list[ProjectItemIn] = Field(default_factory=list, max_length=300)


class ResponseDocument(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    required: bool = True


class ResponseRequirements(BaseModel):
    """Stage 3.8: what a provider must submit with their price. The price
    itself always is, shaped by pricing_basis (one total, or a rate per item)."""

    completion_period: Literal["required", "optional"] = "optional"
    approach: Literal["required", "optional"] = "optional"  # technical proposal / method
    documents: list[ResponseDocument] = Field(default_factory=list, max_length=10)
    declarations: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("declarations")
    @classmethod
    def _clean_declarations(cls, value: list[str]) -> list[str]:
        cleaned = [d.strip() for d in value]
        if any(not d or len(d) > 500 for d in cleaned):
            raise ValueError("Each declaration must be 1-500 characters.")
        return cleaned

    @field_validator("documents")
    @classmethod
    def _unique_document_names(cls, value: list[ResponseDocument]) -> list[ResponseDocument]:
        names = [d.name.strip().lower() for d in value]
        if len(set(names)) != len(names):
            raise ValueError("Each requested document needs a different name.")
        return [ResponseDocument(name=d.name.strip(), required=d.required) for d in value]


class ProjectItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    position: int
    description: str
    quantity: Decimal | None
    unit: str | None
    specification: str | None


class ProjectDetailOut(ProjectOut):
    drawings: list[DrawingOut] = []
    pricing_basis: PricingBasis = PricingBasis.lump_sum
    items: list[ProjectItemOut] = []
    response_requirements: ResponseRequirements = Field(default_factory=ResponseRequirements)
    currency: str = "KWD"
