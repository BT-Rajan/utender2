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
    milestone_id: str | None = None  # Stage 7.7: evidence for this deliverable
    variation_id: str | None = None  # Stage 7.8: a paper of this variation
    execution_update_id: str | None = None  # Stage 7.9: evidence for this progress update
    evidence: bool = False  # Stage 7.9: execution evidence, not a paper of the agreement
    url: str


class ExecutionUpdateOut(BaseModel):
    id: str  # Stage 7.9: evidence can point at it
    sequence: int
    kind: Literal["started", "progress", "on_hold", "resumed", "delivered", "accepted", "returned"]
    party: str
    recorded_by_name: str | None  # the recording side's own members (and admins) only
    note: str | None
    created_at: UTCDateTime
    milestone_id: str | None = None  # Stage 7.7: delivered / accepted / returned
    milestone_title: str | None = None


class TimelineEntry(BaseModel):
    """Stage 7.13: one business event of the transaction, from its own record
    (award, agreement, execution history, variations, documents) -- never
    reconstructed from current values."""

    at: UTCDateTime
    kind: Literal[
        "awarded", "terms_confirmed", "in_force", "document", "started", "progress", "on_hold", "resumed",
        "delivered", "accepted", "returned", "change_proposed", "change_agreed", "change_rejected",
        "change_withdrawn", "change_lapsed", "terminated", "completed",
    ]
    party: Literal["owner", "provider"] | None = None
    actor_name: str | None = None  # the acting member, for the caller's own side (and admins)
    note: str | None = None
    milestone_title: str | None = None  # delivered / accepted / returned of a deliverable
    variation_number: int | None = None
    amount: Decimal | None = None  # awarded value; a change's value change
    resulting_amount: Decimal | None = None  # an agreed change's resulting value
    document_kind: str | None = None
    document_name: str | None = None
    execution_update_id: str | None = None  # its evidence (7.9)


class MilestoneOut(BaseModel):
    """Stage 7.7: one deliverable of the agreement."""

    id: str
    position: int
    title: str
    description: str | None
    due_date: date | None
    project_item_id: str | None
    project_item_label: str | None  # the requirement item it delivers, as the requirement states it
    status: Literal["pending", "delivered", "accepted", "returned"]
    delivered_at: UTCDateTime | None
    delivery_note: str | None
    decided_at: UTCDateTime | None
    decision_note: str | None
    version: int
    variation_number: int | None = None  # Stage 7.8: added by this agreed variation


class VariationOut(BaseModel):
    """Stage 7.8: one proposed or agreed change, with what it changed from."""

    id: str
    number: int
    status: Literal["proposed", "agreed", "rejected", "withdrawn", "lapsed"]
    description: str
    value_change: Decimal | None
    completion_date: date | None
    milestone_id: str | None
    milestone_title: str | None
    milestone_due_date: date | None
    add_deliverable: str | None
    proposed_party: str
    proposed_at: UTCDateTime
    decided_party: str | None
    decided_at: UTCDateTime | None
    decision_note: str | None
    previous_amount: Decimal | None
    resulting_amount: Decimal | None
    previous_completion_date: date | None
    previous_milestone_due_date: date | None
    version: int


class PaymentStageTerm(BaseModel):
    """Batch A: a payment stage of the tender's commercial terms, with its
    share of the current agreed value. Payments themselves are settled between
    the parties outside U-Tender; this states what was agreed."""
    milestone: str
    percent: Decimal
    amount: Decimal


class CommercialTerms(BaseModel):
    """Batch A: the requirement's commercial conditions (fixed when it was
    published) as they apply to this agreement."""
    offer_validity_days: int | None = None
    payment_stages: list[PaymentStageTerm] = []
    retention_percent: Decimal | None = None
    retention_amount: Decimal | None = None
    retention_months: int | None = None
    warranty_months: int | None = None
    # Once the work is accepted as complete: when the defects-liability
    # (warranty) period ends and when the retention falls due for release.
    warranty_until: date | None = None
    retention_release_on: date | None = None


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
    terminated_party: str | None = None  # Batch A: owner / provider
    provider_confirmed_at: UTCDateTime | None = None  # Batch A: the provider confirmed the terms as they stand
    commercial_terms: CommercialTerms | None = None  # Batch A: the tender's commercial conditions, carried into the agreement
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
    execution_status: Literal["not_started", "in_progress", "on_hold", "completed", "terminated"]
    # Stage 7.10: the whole work's completion and what is still outstanding.
    completion_status: Literal["submitted", "accepted", "returned"] | None = None
    completed_at: UTCDateTime | None = None  # Stage 7.11: when the transaction closed
    completion_submitted_at: UTCDateTime | None = None
    completion_note: str | None = None
    completion_decided_at: UTCDateTime | None = None
    completion_decision_note: str | None = None
    outstanding_deliverables: int = 0
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
    # Stage 7.7: the agreement's deliverables, in order (none for a simple job).
    milestones: list[MilestoneOut] = []
    # Stage 7.8: the original award and agreement beside the current agreed
    # state (original + agreed variations), and every variation in order.
    original_amount: Decimal | None = None
    current_amount: Decimal | None = None
    original_completion_date: date | None = None
    original_completion_source: Literal["offer", "requirement"] | None = None
    current_completion_date: date | None = None
    # Stage 7.12: the financial position U-Tender can state truthfully -- the
    # net of the agreed changes (current = original + this), and that payments
    # between the parties are not tracked by U-Tender. Its own billing is the
    # providers' subscription, never a payment against a transaction.
    # Stage 7.13: the transaction's history, in order.
    timeline: list[TimelineEntry] = []
    agreed_changes_total: Decimal = Decimal(0)
    payment_tracking: Literal["not_managed"] = "not_managed"
    variations: list[VariationOut] = []


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


class MilestoneIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    due_date: date | None = None
    project_item_id: str | None = None


class MilestoneNote(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class VariationIn(BaseModel):
    description: str = Field(min_length=1, max_length=4000)
    value_change: Decimal | None = Field(default=None, ge=Decimal("-99999999999"), le=Decimal("99999999999"), decimal_places=3)
    completion_date: date | None = None
    milestone_id: str | None = None
    milestone_due_date: date | None = None
    add_deliverable: str | None = Field(default=None, max_length=200)
