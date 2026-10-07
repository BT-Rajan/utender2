from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.common import UTCDateTime


class ProjectAmendmentRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    trade: str | None = None
    category_id: str | None = None  # one of the platform's service categories (sets trade)
    documents_required: bool | None = None  # providers need the documents to price (Stage 3.12)
    address: str | None = None
    governorate: str | None = None
    area: str | None = None
    bid_deadline: datetime | None = None
    # Stage 3.7 execution timing (send null to clear).
    expected_start_date: date | None = None
    expected_completion_date: date | None = None
    expected_duration_days: int | None = None
    reason: str | None = None


class ProjectAmendmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    amendment_number: int
    summary: str
    changed_fields: str
    reason: str | None
    deadline_extended: bool
    material: bool = False  # Stage 3.15: changed what providers price
    changes: dict | None = None  # Stage 3.17: before/after per field
    material_revision: int = 0  # the requirement version in force after it
    created_by: str
    created_at: UTCDateTime
