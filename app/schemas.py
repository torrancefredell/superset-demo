from datetime import datetime

from pydantic import BaseModel


class SessionLogResponse(BaseModel):
    id: int
    github_issue_number: int
    github_issue_title: str
    devin_session_id: str
    devin_session_url: str | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WebhookResponse(BaseModel):
    message: str
    devin_session_id: str | None = None
    github_issue_number: int | None = None
