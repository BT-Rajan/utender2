from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import gen_uuid
from app.models.enums import MembershipRole


# The commercial identity behind organization-based marketplace activity.
# A login (User) is always a person; when that person acts for a business,
# government body or other organization, the organization is this row and
# the person's link to it is an OrganizationMembership.
#
# Deliberately small: only what the current verification model needs to
# identify the organization. Registration/licence numbers and supporting
# evidence are captured by each side's existing verification step
# (ServiceProviderProfile.license_number and the admin-configured
# document requirements), so they are not duplicated here.
class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    memberships = relationship("OrganizationMembership", back_populates="organization", cascade="all, delete-orphan")


# Person -> organization. Many people may belong to one organization; the
# person who establishes it is its first admin (authorized representative).
class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_organization_member"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[MembershipRole] = mapped_column(Enum(MembershipRole, native_enum=True), nullable=False)
    # The representative's capacity, e.g. "General Manager" -- what an admin
    # reviewing the organization's documents checks the authority against.
    position: Mapped[str | None] = mapped_column(String(150), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    organization = relationship("Organization", back_populates="memberships")
    user = relationship("User")
