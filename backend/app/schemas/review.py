from datetime import datetime
from typing import Literal

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


class ReviewResponseCreate(BaseModel):
    """Stage 8.9: only the text -- the review, the responding side and the time all come from the server."""
    response: str = Field(min_length=1, max_length=2000)


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
    # Stage 8.9: the reviewed side's response, if any -- unless an admin hid it (8.15).
    response: str | None = Field(default=None, validation_alias="shown_response")
    response_at: UTCDateTime | None = Field(default=None, validation_alias="shown_response_at")
    hidden: bool = Field(default=False, validation_alias="is_hidden")  # Stage 8.15: an admin hid this review


class ReceivedReviewOut(BaseModel):
    """Stage 8.6: the review a party received, as that party sees it -- the
    rating, comment and date only. No ids, no reviewer account, nothing of the
    transaction: the reviewed party already knows its counterparty."""
    model_config = ConfigDict(from_attributes=True)

    rating: int
    comment: str | None
    created_at: UTCDateTime
    # Stage 8.9: the reviewed side's response, beside the review -- unless an admin hid it (8.15).
    response: str | None = Field(default=None, validation_alias="shown_response")
    response_at: UTCDateTime | None = Field(default=None, validation_alias="shown_response_at")


class ProviderReputationOut(BaseModel):
    """Stage 8.7: a provider's reputation from completed U-Tender transactions
    -- counts, the simple average of owner reviews (None until there is one)
    and the latest owner reviews, each as rating, comment and date only."""
    company_name: str | None
    completed_transactions: int
    terminated_transactions: int = 0  # Batch A: agreements ended before completion, by either party
    review_count: int
    avg_rating: float | None
    recent_reviews: list[ReceivedReviewOut]
    # Stage 8.12: only for an owner weighing the provider's offer -- the
    # transactions its own organisation completed with this provider.
    completed_with_you: int | None = None


class OwnerReputationOut(BaseModel):
    """Stage 8.8: an owner's reputation from completed U-Tender transactions
    -- counts and the simple average of provider reviews (None until there is
    one). recent_reviews is filled only for the owner side itself and admin:
    providers weighing a requirement don't yet know whose it is (Stage 7.2),
    and review text could tell them."""
    completed_transactions: int
    terminated_transactions: int = 0  # Batch A: agreements ended before completion, by either party
    review_count: int
    avg_rating: float | None
    recent_reviews: list[ReceivedReviewOut]


class PreviousTransactionOut(BaseModel):
    project_id: str
    title: str
    completed_at: UTCDateTime | None


class PreviousProviderOut(BaseModel):
    """Stage 8.12: a provider the owner organisation completed work with --
    its name and those completed requirements, nothing else of them."""
    company_name: str | None
    completed_transactions: int
    last_completed_at: UTCDateTime | None
    transactions: list[PreviousTransactionOut]


class PreviousOwnerOut(BaseModel):
    """Stage 8.13: an owner the provider organisation completed work for --
    its name and those completed requirements; no contact details."""
    owner_name: str | None
    completed_transactions: int
    last_completed_at: UTCDateTime | None
    transactions: list[PreviousTransactionOut]


class ReviewReportCreate(BaseModel):
    """Stage 8.15: what is reported (the review your side received, or the
    response to your side's review), why, and an optional short note. The
    review and the reporter come from the server."""
    target: Literal["review", "response"]
    reason: Literal["abusive", "private_information", "not_about_this_transaction", "other"]
    note: str | None = Field(default=None, max_length=500)


class ReviewReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    target: str
    reason: str
    status: str
    created_at: UTCDateTime


class ModerationDecision(BaseModel):
    decision: Literal["keep", "hide"]
    note: str | None = Field(default=None, max_length=1000)


class ReviewReportAdminOut(BaseModel):
    """Stage 8.15: one report as an admin decides it -- the report, what was
    reported (as written, even if hidden since), and who the two parties are.
    Nothing else of the transaction."""
    id: str
    target: str
    reason: str
    note: str | None
    status: str
    created_at: UTCDateTime
    resolved_at: UTCDateTime | None
    resolution_note: str | None
    reported_by: str  # the side: "owner" or "service_provider"
    direction: str
    rating: int
    comment: str | None
    response: str | None
    review_hidden: bool
    response_hidden: bool
    project_title: str
    owner_name: str | None
    provider_name: str | None
