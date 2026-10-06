"""Kuwait's six governorates, the level at which providers judge whether a
site is within their service area. Stored as these keys on
Project.governorate; display names live in the frontend dictionaries. Adding
another market's regions means extending this list (and those names)."""
from fastapi import HTTPException

KUWAIT_GOVERNORATES = ("capital", "hawalli", "farwaniya", "mubarak_al_kabeer", "ahmadi", "jahra")


def clean_governorate(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    if value not in KUWAIT_GOVERNORATES:
        raise HTTPException(status_code=400, detail="Unknown governorate.")
    return value


def clean_area(value: str | None) -> str | None:
    value = (value or "").strip()
    if len(value) > 100:
        raise HTTPException(status_code=400, detail="Area must be 100 characters or fewer.")
    return value or None
