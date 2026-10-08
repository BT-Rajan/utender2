from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.schemas.common import UTCDateTime


class AwardRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    # Stage 6.16: the winning offer's id, provider and price go to the owner's
    # side, admins and the winner -- never to the other bidders.
    offer_id: str | None
    service_provider_id: str | None
    amount: Decimal | None
    project_revision: int
    offer_revision: int | None
    awarded_by: str | None
    created_at: UTCDateTime  # Stage 7.1: when it was awarded (UTC)
    service_provider_company_name: str | None = None
    mine: bool = False  # Stage 6.16: the reader's side won it
    # Stage 7.1: the requirement version the awarded offer answered.
    material_revision: int | None = None
