from datetime import datetime, timezone
from typing import Annotated

from pydantic import PlainSerializer


def utc_iso(value: datetime | None) -> str | None:
    """Timestamps are stored as naive UTC (see datetime.utcnow() throughout).
    Serialising them without a zone made browsers read them as *local* time,
    so a deadline displayed and counted down hours away from the moment the
    server enforces it. Mark them as UTC explicitly."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# A naive-UTC datetime that serialises with an explicit "Z".
UTCDateTime = Annotated[datetime, PlainSerializer(utc_iso, return_type=str, when_used="json")]
