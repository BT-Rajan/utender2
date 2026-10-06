from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import gen_uuid
from app.models.enums import Language, UserRole


# Replaces the Supabase auth.users + profiles split — this app now owns
# authentication itself, so identity and role/profile fields live in one
# table.
class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, native_enum=True), nullable=False, default=UserRole.owner)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    language: Mapped[Language] = mapped_column(Enum(Language, native_enum=True), nullable=False, default=Language.en)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    service_provider_profile = relationship(
        "ServiceProviderProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    owner_profile = relationship(
        "OwnerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
