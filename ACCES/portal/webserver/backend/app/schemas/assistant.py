from datetime import datetime

from pydantic import BaseModel


class AssistantEventOut(BaseModel):
    id: str
    project_id: str
    kind: str
    source: str
    confidence: str
    summary: str
    detail_json: str
    timestamp: datetime

    model_config = {"from_attributes": True}


class AssistantMessageOut(BaseModel):
    id: str
    project_id: str
    role: str
    content: str
    timestamp: datetime

    model_config = {"from_attributes": True}


class AskRequest(BaseModel):
    question: str


class FindingOut(BaseModel):
    observation: str
    analysis: str
    possible_problem: str
    evidence: str
    suggestion: str
    confidence: str  # AssistantConfidence value


class AskResponse(BaseModel):
    message: str
    mode: str  # "finding" | "teaching" | "general"
    findings: list[FindingOut] = []
    events: list[AssistantEventOut] = []
