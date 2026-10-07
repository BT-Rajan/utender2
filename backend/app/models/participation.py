from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import gen_uuid


# Stage 4.9: a provider decided to take part in a requirement -- the step from
# looking at an opportunity to preparing an offer for it. One per provider
# stakeholder and requirement (an organization's members share it, like its
# offer); recorded only when every participation check passes, and by any
# offer submitted (offering is deciding). Nothing is sent to the owner: it
# is the provider's own working state. seen_material_revision is the version
# of the requirement they decided on, so a later material change is flagged.
class Participation(Base):
    __tablename__ = "participations"
    # Stage 5.1: one per stakeholder, like offers -- and per organization (NULLs,
    # individuals, are distinct to the database, so this only binds organizations).
    __table_args__ = (
        UniqueConstraint("project_id", "service_provider_id", name="uq_participation"),
        UniqueConstraint("project_id", "organization_id", name="uq_participation_organization"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    service_provider_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("service_provider_profiles.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    started_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    seen_material_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
