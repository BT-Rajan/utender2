from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import gen_uuid
from app.models.enums import ProjectStatus, TenderType


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    trade: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bid_deadline: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, native_enum=True), nullable=False, default=ProjectStatus.open, index=True
    )
    # Owner's choice at creation (spec §19-21, D-001): Sealed hides bidder
    # identity/amount/message/attachments from the owner until close;
    # Owner-Visible lets the owner see bids as they arrive. Locked once
    # tender_type_locked flips true (first valid bid submitted) — a
    # material tender condition can't be changed mid-bidding.
    tender_type: Mapped[TenderType] = mapped_column(
        Enum(TenderType, native_enum=True), nullable=False, default=TenderType.owner_visible
    )
    tender_type_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Admin moderation flag — independent of the owner-driven lifecycle
    # `status` above. Hides the project from the service provider feed and blocks
    # new bids while set, but leaves `status` untouched so un-suspending
    # restores exactly the state the project was in before.
    is_suspended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Sequential per project; bumped by the amendment service whenever a
    # published tender's material fields change (spec §2.8/§2.12).
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deadline_reminder_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    drawings = relationship("ProjectDrawing", back_populates="project", cascade="all, delete-orphan")


class ProjectDrawing(Base):
    __tablename__ = "project_drawings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    # Versioning (spec §2.8, §25, §67): a revised drawing is a NEW row, not
    # an overwrite of the old one. is_current marks which row is the one
    # service providers should look at; superseded rows stay in the database and
    # in storage for audit purposes.
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    amendment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("project_amendments.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    project = relationship("Project", back_populates="drawings")
