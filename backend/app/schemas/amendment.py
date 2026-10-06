from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProjectAmendmentRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    trade: str | None = None
    address: str | None = None
    governorate: str | None = None
    area: str | None = None
    bid_deadline: datetime | None = None
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
    created_by: str
    created_at: datetime
