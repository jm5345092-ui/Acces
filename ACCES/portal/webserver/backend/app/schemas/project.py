from datetime import datetime

from pydantic import BaseModel


class ProjectOut(BaseModel):
    id: str
    name: str
    created_at: datetime
    original_filename: str
    sha256: str
    sha1: str
    size_bytes: int
    package_name: str
    version_code: str
    version_name: str
    min_sdk: str
    target_sdk: str
    status: str

    model_config = {"from_attributes": True}


class ProjectCreate(BaseModel):
    name: str


class AnalysisOut(BaseModel):
    manifest: dict
    dex: dict
    certificate: dict
    resources: dict
