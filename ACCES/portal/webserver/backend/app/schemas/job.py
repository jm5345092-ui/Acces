from datetime import datetime

from pydantic import BaseModel


class JobOut(BaseModel):
    id: str
    project_id: str
    type: str
    status: str
    progress: int
    result_json: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
