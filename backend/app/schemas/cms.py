from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import Language


class CmsContentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    key: str
    language: Language
    value: str
    updated_at: datetime


class CmsContentUpsert(BaseModel):
    value: str


class PublicStatsOut(BaseModel):
    open_tenders: int
    verified_contractors: int
    awarded_projects: int
    total_awarded_value: Decimal


class PublicRequirementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    description: str | None
    is_required: bool


class PublicPlanPriceOut(BaseModel):
    plan: str  # "monthly" | "annual" -- the value /billing/checkout-session takes
    amount: Decimal  # in major units, e.g. 79.00
    currency: str  # lowercase ISO code, as Stripe returns it
    interval: str  # "month" | "year" | ...
    interval_count: int


class PublicPricingOut(BaseModel):
    plans: list[PublicPlanPriceOut]
