from pydantic import BaseModel, EmailStr, HttpUrl
from typing import List, Optional


class Attachment(BaseModel):
    name: str
    url: str  # data URI format


class BuildRequest(BaseModel):
    email: EmailStr
    secret: str
    task: str
    round: int
    nonce: str
    brief: str
    checks: List[str]
    evaluation_url: HttpUrl
    attachments: List[Attachment] = []


class BuildResponse(BaseModel):
    status: str
    message: str
    task: Optional[str] = None
    round: Optional[int] = None


class EvaluationPayload(BaseModel):
    email: EmailStr
    task: str
    round: int
    nonce: str
    repo_url: str
    commit_sha: str
    pages_url: str
