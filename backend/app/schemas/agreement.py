from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import UTCDateTime


class AgreementDocumentOut(BaseModel):
    id: str
    kind: str
    party: str
    file_name: str
    uploaded_at: UTCDateTime
    uploaded_by_name: str | None = None  # Stage 7.4: the caller's own side's documents only
    url: str


class AgreementOut(BaseModel):
    """Stage 7.3: the agreement, with the award it governs read straight from
    the award record -- never a copy that could drift from it."""

    id: str
    status: str
    reference: str | None
    effective_date: date | None
    activated_at: UTCDateTime | None
    terminated_at: UTCDateTime | None
    termination_reason: str | None
    version: int
    created_at: UTCDateTime
    updated_at: UTCDateTime | None
    # The award: the requirement, the winning offer, the parties, the value.
    award_id: str
    awarded_at: UTCDateTime
    project_id: str
    project_title: str
    offer_id: str
    offer_revision: int
    material_revision: int | None
    amount: Decimal
    currency: str
    owner_name: str | None
    provider_name: str | None
    side: Literal["owner", "provider", "admin"]
    documents: list[AgreementDocumentOut]


class AgreementUpdate(BaseModel):
    reference: str | None = Field(default=None, max_length=120)
    effective_date: date | None = None


class AgreementTerminate(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
