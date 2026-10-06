from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ClarificationCreate(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    shared_with_all: bool = True


class ClarificationAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)


class ClarificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    # None when redacted for the owner on a still-sealed-and-open tender
    # (spec §19-21, D-001) — see clarifications.py's list_clarifications.
    service_provider_id: str | None
    question: str
    answer: str | None
    shared_with_all: bool
    created_at: datetime
    answered_at: datetime | None
    service_provider_company_name: str | None = None
