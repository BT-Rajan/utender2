from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import gen_uuid


# Stage 4.8: an opportunity a provider marked to come back to. Belongs to the
# provider stakeholder, like its offers and questions (services.team): an
# organization's members share one list. Nothing about the requirement
# changes; the row only points at it. One per provider and requirement.
class SavedOpportunity(Base):
    __tablename__ = "saved_opportunities"
    __table_args__ = (UniqueConstraint("project_id", "service_provider_id", name="uq_saved_opportunity"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    service_provider_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("service_provider_profiles.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    saved_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
