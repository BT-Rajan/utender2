from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import DocumentStatus, StakeholderType, UserRole


class DocumentRequirementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    is_required: bool
    is_active: bool
    applies_to: UserRole
    applies_to_stakeholder: StakeholderType | None = None  # None = individuals and organizations
    requires_expiry: bool = False
    effective_from: datetime
    created_at: datetime


class DocumentRequirementCreate(BaseModel):
    name: str
    description: str | None = None
    is_required: bool = True
    applies_to: UserRole = UserRole.service_provider
    applies_to_stakeholder: StakeholderType | None = None
    requires_expiry: bool = False

    @field_validator("applies_to")
    @classmethod
    def _no_admin_requirements(cls, value: UserRole) -> UserRole:
        if value == UserRole.admin:
            raise ValueError("Document requirements can only apply to owners or service providers.")
        return value


class ServiceProviderDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    service_provider_id: str
    requirement_id: str
    status: DocumentStatus
    admin_note: str | None
    reviewed_at: datetime | None
    submitted_at: datetime | None
    expires_on: date | None = None
    requirement_name: str | None = None
    requirement_description: str | None = None
    requirement_is_required: bool | None = None
    # Lets the admin UI flag "approved before this requirement's terms
    # last changed" without a second round trip.
    requirement_effective_from: datetime | None = None
    requirement_requires_expiry: bool | None = None


class ReviewDocumentDecision(BaseModel):
    service_provider_id: str
    requirement_id: str
    decision: DocumentStatus
    note: str | None = None
    expires_on: date | None = None


class DocumentExpiryUpdate(BaseModel):
    expires_on: date | None = None


class OwnerDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    requirement_id: str
    status: DocumentStatus
    admin_note: str | None
    reviewed_at: datetime | None
    submitted_at: datetime | None
    expires_on: date | None = None
    requirement_name: str | None = None
    requirement_description: str | None = None
    requirement_is_required: bool | None = None
    requirement_effective_from: datetime | None = None
    requirement_requires_expiry: bool | None = None


class ReviewOwnerDocumentDecision(BaseModel):
    owner_id: str
    requirement_id: str
    decision: DocumentStatus
    note: str | None = None
    expires_on: date | None = None
