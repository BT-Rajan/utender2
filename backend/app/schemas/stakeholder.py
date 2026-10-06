from pydantic import BaseModel

from app.models.enums import StakeholderType


class StakeholderEstablish(BaseModel):
    type: StakeholderType
    # Organization only:
    legal_name: str | None = None
    position: str | None = None  # the representative's capacity, e.g. "General Manager"
    # The person confirms they may act for the organization; they become its
    # first authorized representative (membership role "admin").
    authorized: bool = False


class PersonOut(BaseModel):
    user_id: str
    full_name: str | None
    email: str


class MembershipOut(BaseModel):
    role: str  # "admin" (authorized representative) | "member"
    position: str | None


class RepresentativeOut(BaseModel):
    user_id: str
    full_name: str | None
    email: str
    position: str | None


class OrganizationOut(BaseModel):
    id: str
    legal_name: str
    member_count: int
    membership: MembershipOut | None  # the viewing person's relationship to it
    authorized_representative: RepresentativeOut | None


class StakeholderStatusOut(BaseModel):
    account_created: bool
    stakeholder_established: bool
    verified: bool  # for an organization stakeholder: the organization is verified
    eligible: bool  # may participate in the marketplace right now
    verification_status: str
    marketplace_status: str


class StakeholderOut(BaseModel):
    id: str  # the id projects/offers/reviews are recorded under
    side: str  # "owner" | "service_provider"
    type: StakeholderType | None  # None = not established yet
    display_name: str | None
    organization: OrganizationOut | None
    status: StakeholderStatusOut
    editable: bool


class ActingAsOut(BaseModel):
    kind: str  # "individual" | "organization"
    stakeholder_id: str
    name: str | None
    user_id: str | None = None
    organization_id: str | None = None


class IdentityOut(BaseModel):
    person: PersonOut
    role: str
    stakeholder: StakeholderOut | None  # None for admins
    acting_as: ActingAsOut | None  # None until the stakeholder is established
