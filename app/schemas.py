from datetime import datetime

from pydantic import BaseModel


class SessionLogResponse(BaseModel):
    id: int
    github_issue_number: int
    github_issue_title: str
    devin_session_id: str
    devin_session_url: str | None
    status: str
    status_detail: str | None
    pull_request_url: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WebhookResponse(BaseModel):
    message: str
    devin_session_id: str | None = None
    github_issue_number: int | None = None


class MetricsResponse(BaseModel):
    total_sessions: int
    by_status: dict[str, int]
    success_rate: str
    sessions_with_prs: int
    latest_session: SessionLogResponse | None
