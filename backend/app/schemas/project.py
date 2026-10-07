from datetime import date, datetime
from decimal import Decimal

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    # Stage 3.11: last saved, and whether a draft was discarded.
    updated_at: UTCDateTime | None = None
    discarded_at: UTCDateTime | None = None
    published_at: UTCDateTime | None = None  # set by the server on publication
    version: int = 1  # send back as If-Match when saving a draft
    documents_required: bool = False
    offer_count: int = 0
    my_offer_status: str | None = None  # only populated on the service provider feed
    # Stage 3.9, service provider feed only: whether this provider may respond,
    # and if not, why.
    eligible: bool | None = None
    ineligible_reasons: list["EligibilityReason"] = Field(default_factory=list)
    category_id: str | None = None


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


class ProviderEligibilityIn(BaseModel):
    """Stage 3.9: who may respond to this requirement, beyond being a
    verified provider with active access (always required). Both parts are
    optional; the default is every such provider. Qualifications are ids of
    the platform's own provider verification requirements (the admin-managed
    DocumentRequirement list) -- nothing here names a specific document."""

    provider_type: Literal["any", "organization"] = "any"
    qualifications: list[str] = Field(default_factory=list, max_length=5)
    # Only providers who list this requirement's service category / serve
    # its governorate (as declared on their profile).
    match_category: bool = False
    match_governorate: bool = False

    @field_validator("qualifications")
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class EligibilityQualification(BaseModel):
    id: str
    name: str
    description: str | None = None


class ProviderEligibilityOut(BaseModel):
    provider_type: Literal["any", "organization"] = "any"
    qualifications: list[EligibilityQualification] = Field(default_factory=list)
    match_category: bool = False
    match_governorate: bool = False
    category: str | None = None  # the requirement's category name, when matched on
    governorate: str | None = None  # the requirement's governorate key, when matched on


class EligibilityReason(BaseModel):
    """One reason, as a code the interface translates (organization_only,
    qualification_missing, qualification_expired, category_not_offered,
    governorate_not_served) plus its details, and the English sentence used
    in API errors."""

    code: str
    name: str | None = None  # qualification or category name
    date: str | None = None  # expiry date (ISO)
    governorate: str | None = None
    message: str


class EligibilityCheckOut(BaseModel):
    """A provider's own standing against one requirement, with the reasons
    when they can't respond -- never an unexplained refusal."""

    eligible: bool
    reasons: list[EligibilityReason] = Field(default_factory=list)
    rules: ProviderEligibilityOut


class PaymentStage(BaseModel):
    milestone: str = Field(min_length=1, max_length=200)  # e.g. "On mobilisation"
    percent: Decimal = Field(gt=0, le=100, decimal_places=2)


class CommercialConditions(BaseModel):
    """Stage 3.10: the commercial terms owners most often set, as fields
    providers can read at a glance. All optional; state only what applies."""

    offer_validity_days: int | None = Field(default=None, ge=1, le=365)  # prices held after offers close
    payment_stages: list[PaymentStage] = Field(default_factory=list, max_length=10)
    retention_percent: Decimal | None = Field(default=None, gt=0, le=100, decimal_places=2)
    retention_months: int | None = Field(default=None, ge=1, le=120)
    warranty_months: int | None = Field(default=None, ge=1, le=240)  # defects liability from handover

    @model_validator(mode="after")
    def _consistent(self):
        if self.payment_stages and sum(s.percent for s in self.payment_stages) != 100:
            raise ValueError("Payment stages must add up to 100%.")
        if (self.retention_percent is None) != (self.retention_months is None):
            raise ValueError("Give both the retention percentage and how long it is held.")
        return self


class TenderRulesIn(BaseModel):
    """Stage 3.10: the rules of participation the owner sets on a draft. The
    offer deadline itself is set with the dates (Stage 3.7)."""

    tender_type: TenderType = TenderType.owner_visible
    questions_allowed: bool = True
    questions_deadline: datetime | None = None  # with an offset; None = until offers close
    commercial_conditions: CommercialConditions = Field(default_factory=CommercialConditions)
    commercial_terms: str | None = Field(default=None, max_length=5000)  # other conditions
    bidder_instructions: str | None = Field(default=None, max_length=5000)


class TenderRulesOut(BaseModel):
    questions_allowed: bool = True
    questions_deadline: UTCDateTime | None = None
    # Derived from the authoritative rules (services.tender_rules), so the
    # page says exactly what the server will do.
    questions_close_at: UTCDateTime | None = None
    questions_open: bool = False
    commercial_conditions: CommercialConditions = Field(default_factory=CommercialConditions)
    commercial_terms: str | None = None
    bidder_instructions: str | None = None


class ProjectItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    position: int
    description: str
    quantity: Decimal | None
    unit: str | None
    specification: str | None


ProjectOut.model_rebuild()


class ProjectDetailOut(ProjectOut):
    drawings: list[DrawingOut] = []
    pricing_basis: PricingBasis = PricingBasis.lump_sum
    items: list[ProjectItemOut] = []
    provider_eligibility: ProviderEligibilityOut = Field(default_factory=ProviderEligibilityOut)
    response_requirements: ResponseRequirements = Field(default_factory=ResponseRequirements)
    tender_rules: TenderRulesOut = Field(default_factory=TenderRulesOut)
    currency: str = "KWD"
