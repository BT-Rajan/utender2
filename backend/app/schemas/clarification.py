from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import UTCDateTime


class ClarificationCreate(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    shared_with_all: bool = True


class ClarificationAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)
    # Stage 4.7: the owner may publish the answer to a privately asked
    # question for every provider, when it matters to how all of them read
    # the requirement (the asker stays anonymous). None = as the asker chose.
    shared_with_all: bool | None = None


class ClarificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    # None when redacted: for another provider always, and for the owner on
    # a still-sealed-and-open tender (spec §19-21, D-001).
    service_provider_id: str | None
    question: str
    answer: str | None
    shared_with_all: bool
    created_at: UTCDateTime
    answered_at: UTCDateTime | None
    service_provider_company_name: str | None = None
    # Stage 4.7: asked by the viewer's own side; who answered (the owner side
    # and admins only); the amendment the answer came with, if any.
    mine: bool = False
    answered_by_name: str | None = None
    amendment_number: int | None = None
