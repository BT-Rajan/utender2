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


class ExecutionUpdateOut(BaseModel):
    sequence: int
    kind: Literal["started", "progress", "on_hold", "resumed"]
    party: str
    recorded_by_name: str | None  # the recording side's own members (and admins) only
    note: str | None
    created_at: UTCDateTime


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
    # Stage 7.5: execution. The planned start is the winning offer's own
    # commitment, else the requirement's expected start; the actual start is
    # server time, recorded once.
    execution_status: Literal["not_started", "in_progress", "on_hold", "terminated"]
    on_hold_since: UTCDateTime | None  # Stage 7.6
    planned_start_date: date | None
    planned_start_source: Literal["offer", "requirement"] | None
    work_started_at: UTCDateTime | None
    work_started_party: str | None
    work_started_by_name: str | None  # the recording side's own members (and admins) only
    work_start_note: str | None
    side: Literal["owner", "provider", "admin"]
    documents: list[AgreementDocumentOut]
    # Stage 7.6: what the parties recorded since the work started, oldest first.
    execution_history: list["ExecutionUpdateOut"] = []


class AgreementUpdate(BaseModel):
    reference: str | None = Field(default=None, max_length=120)
    effective_date: date | None = None


class AgreementTerminate(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class WorkStart(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class ExecutionProgress(BaseModel):
    """Stage 7.6: a short progress note, or putting the work on hold, or resuming it."""

    action: Literal["update", "hold", "resume"]
    note: str | None = Field(default=None, max_length=2000)
