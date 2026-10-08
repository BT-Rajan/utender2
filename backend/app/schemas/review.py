from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import UTCDateTime


class ReviewCreate(BaseModel):
    project_id: str
    # Accepted for backward compatibility with existing callers but IGNORED
    # server-side — the reviewed service provider is always derived from the
    # project's own AwardRecord (see owner.py's submit_review), never taken
    # from client input.
    service_provider_id: str | None = None
    owner_id: str | None = None  # Stage 8.4: likewise ignored -- the parties come from the transaction
    rating: int = Field(ge=1, le=5, strict=True)  # a whole number 1-5; nothing else is coerced into one
    comment: str | None = Field(default=None, max_length=2000)


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    owner_id: str
    service_provider_id: str
    rating: int
    comment: str | None
    direction: str  # Stage 8.4: owner_to_provider / provider_to_owner
    created_at: UTCDateTime
