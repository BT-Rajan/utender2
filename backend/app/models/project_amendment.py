from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import gen_uuid


# A numbered, permanent record of a material change to a published tender
# (spec §2.8, D-007). changed_fields is a human-readable summary (e.g.
# "bid_deadline, description") rather than a structured diff — enough for
# the audit trail and the bidder-facing notification without needing a
# generic diffing engine.
class ProjectAmendment(Base):
    __tablename__ = "project_amendments"
    __table_args__ = (UniqueConstraint("project_id", "amendment_number", name="uq_project_amendment_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amendment_number: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    changed_fields: Mapped[str] = mapped_column(String(500), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline_extended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Stage 3.15: changes what providers price (scope, location, work timing,
    # type of work, documents) -- as opposed to a title correction or more time.
    material: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="0")
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
