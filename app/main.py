import hashlib
import hmac
import logging
from datetime import datetime, timezone

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, engine, get_db
from app.models import SessionLog
from app.schemas import SessionLogResponse, WebhookResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Superset Issue Automator",
    description="Listens for GitHub issue events and triggers Devin sessions to fix them.",
    version="1.0.0",
)


def verify_github_signature(payload_body: bytes, signature: str | None) -> bool:
    if not settings.github_webhook_secret:
        return True
    if not signature:
        return False
    expected = hmac.new(
        settings.github_webhook_secret.encode(),
        payload_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


async def create_devin_session(prompt: str) -> dict:
    url = (
        f"{settings.devin_api_base_url}"
        f"/organizations/{settings.devin_org_id}/sessions"
    )
    headers = {
        "Authorization": f"Bearer {settings.devin_api_token}",
        "Content-Type": "application/json",
    }
    body = {"prompt": prompt}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=body, headers=headers)
        response.raise_for_status()
        return response.json()


@app.post("/webhook", response_model=WebhookResponse)
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(None),
    x_hub_signature_256: str | None = Header(None),
    db: Session = Depends(get_db),
) -> WebhookResponse:
    body = await request.body()

    if not verify_github_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()

    if x_github_event != "issues":
        return WebhookResponse(message=f"Ignored event: {x_github_event}")

    action = payload.get("action")
    if action != "opened":
        return WebhookResponse(message=f"Ignored action: {action}")

    issue = payload.get("issue", {})
    issue_number = issue.get("number")
    issue_title = issue.get("title", "")
    issue_body = issue.get("body", "") or ""
    repo_full_name = payload.get("repository", {}).get("full_name", "")
    repo_url = payload.get("repository", {}).get("html_url", settings.target_repo_url)

    prompt = (
        f"A new GitHub issue has been opened in {repo_full_name}.\n\n"
        f"Issue #{issue_number}: {issue_title}\n\n"
        f"Description:\n{issue_body}\n\n"
        f"Please:\n"
        f"1. Clone the repository: {repo_url}\n"
        f"2. Analyze the issue and implement a fix\n"
        f"3. Open a pull request with the fix, referencing issue #{issue_number}"
    )

    logger.info("Creating Devin session for issue #%s: %s", issue_number, issue_title)

    try:
        devin_response = await create_devin_session(prompt)
    except httpx.HTTPStatusError as exc:
        logger.error("Devin API error: %s – %s", exc.response.status_code, exc.response.text)
        raise HTTPException(
            status_code=502,
            detail=f"Devin API returned {exc.response.status_code}",
        ) from exc
    except httpx.RequestError as exc:
        logger.error("Devin API request failed: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to reach Devin API") from exc

    devin_session_id = devin_response.get("devin_id", "")
    devin_session_url = devin_response.get("url", "")

    log_entry = SessionLog(
        github_issue_number=issue_number,
        github_issue_title=issue_title,
        devin_session_id=devin_session_id,
        devin_session_url=devin_session_url,
        status="Started",
        created_at=datetime.now(timezone.utc),
    )
    db.add(log_entry)
    db.commit()

    logger.info(
        "Devin session created: %s for issue #%s",
        devin_session_id,
        issue_number,
    )

    return WebhookResponse(
        message="Devin session created",
        devin_session_id=devin_session_id,
        github_issue_number=issue_number,
    )


@app.get("/status", response_model=list[SessionLogResponse])
def get_status(db: Session = Depends(get_db)) -> list[SessionLogResponse]:
    logs = db.query(SessionLog).order_by(SessionLog.created_at.desc()).all()
    return [SessionLogResponse.model_validate(log) for log in logs]


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
