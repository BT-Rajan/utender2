from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import gen_uuid


# Permanent record created in the same transaction as an award (spec §34,
# §87). Snapshots project_revision/offer_revision so the award always
# points at the exact tender and bid state that was actually awarded, even
# if later disputes reference tender/bid history around it.
class AwardRecord(Base):
    __tablename__ = "award_records"
    __table_args__ = (UniqueConstraint("project_id", name="uq_award_project"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    offer_id: Mapped[str] = mapped_column(String(36), ForeignKey("offers.id"), nullable=False)
    service_provider_id: Mapped[str] = mapped_column(String(36), ForeignKey("service_provider_profiles.user_id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 3), nullable=False)
    project_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    offer_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    awarded_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
