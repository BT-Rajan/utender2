from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PricingBasis, ProjectStatus, TenderType


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
    url: str | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    title: str
    address: str
    description: str | None
    trade: str | None
    bid_deadline: datetime
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
