from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class AwardRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    offer_id: str
    service_provider_id: str
    amount: Decimal
    project_revision: int
    offer_revision: int
    awarded_by: str
    created_at: datetime
    service_provider_company_name: str | None = None
