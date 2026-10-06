from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    is_active: bool
    created_at: datetime | None = None


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Enter a name.")
        return value


class CategoryPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None


class ProviderServices(BaseModel):
    """What a provider offers (service category ids) and where
    (governorate keys; empty = all of Kuwait)."""

    categories: list[str] = Field(default_factory=list, max_length=50)
    governorates: list[str] = Field(default_factory=list, max_length=10)
