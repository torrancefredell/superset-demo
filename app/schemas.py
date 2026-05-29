from pydantic import BaseModel


class WebhookResponse(BaseModel):
    message: str
    devin_session_id: str | None = None
    devin_session_url: str | None = None
    alert_url: str | None = None
    rule_description: str | None = None
    file_path: str | None = None
