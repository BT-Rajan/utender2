from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import VerificationStatus


class OwnerProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    verification_status: VerificationStatus
    is_suspended: bool
    # Derived, never stored — same shape as ServiceProviderProfileOut's
    # marketplace_status: one of documents_incomplete, submitted_for_review,
    # changes_requested, verified_active, suspended.
    marketplace_status: str
    created_at: datetime
    # Step 4 lifecycle: not_started | incomplete | submitted | under_review |
    # correction_required | approved | rejected (derived; verification_status
    # stays the stored source of truth).
    verification_state: str = "not_started"
    verification_note: str | None = None
    verification_submitted_at: datetime | None = None
    email: str | None = None
    full_name: str | None = None
    project_count: int = 0
