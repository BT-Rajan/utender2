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
    response: str | None = None  # Stage 8.9: the reviewed side's response, if any
    response_at: UTCDateTime | None = None


class ReceivedReviewOut(BaseModel):
    """Stage 8.6: the review a party received, as that party sees it -- the
    rating, comment and date only. No ids, no reviewer account, nothing of the
    transaction: the reviewed party already knows its counterparty."""
    model_config = ConfigDict(from_attributes=True)

    rating: int
    comment: str | None
    created_at: UTCDateTime
    response: str | None = None  # Stage 8.9: the reviewed side's response, beside the review
    response_at: UTCDateTime | None = None


class ProviderReputationOut(BaseModel):
    """Stage 8.7: a provider's reputation from completed U-Tender transactions
    -- counts, the simple average of owner reviews (None until there is one)
    and the latest owner reviews, each as rating, comment and date only."""
    company_name: str | None
    completed_transactions: int
    review_count: int
    avg_rating: float | None
    recent_reviews: list[ReceivedReviewOut]


class OwnerReputationOut(BaseModel):
    """Stage 8.8: an owner's reputation from completed U-Tender transactions
    -- counts and the simple average of provider reviews (None until there is
    one). recent_reviews is filled only for the owner side itself and admin:
    providers weighing a requirement don't yet know whose it is (Stage 7.2),
    and review text could tell them."""
    completed_transactions: int
    review_count: int
    avg_rating: float | None
    recent_reviews: list[ReceivedReviewOut]
