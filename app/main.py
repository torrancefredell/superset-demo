import hashlib
import hmac
import logging
from collections import Counter
from datetime import datetime, timezone

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, engine, get_db
from app.models import SessionLog
from app.schemas import MetricsResponse, SessionLogResponse, WebhookResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Superset Issue Automator",
    description=(
        "Event-driven automation that listens for GitHub issue events "
        "and triggers Devin AI sessions to remediate them."
    ),
    version="1.0.0",
)

TRIGGER_PREFIX = "/devin"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


async def call_devin_api(method: str, path: str, json_body: dict | None = None) -> dict:
    url = f"{settings.devin_api_base_url}{path}"
    headers = {
        "Authorization": f"Bearer {settings.devin_api_token}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        if method == "GET":
            response = await client.get(url, headers=headers)
        else:
            response = await client.post(url, json=json_body, headers=headers)
        response.raise_for_status()
        return response.json()


def map_devin_status(status: str, status_detail: str | None) -> str:
    """Map Devin API status/status_detail to a human-readable label."""
    if status == "exit" and status_detail == "finished":
        return "completed"
    if status == "error":
        return "failed"
    if status in ("running", "claimed", "resuming"):
        return "running"
    if status == "suspended":
        return "blocked"
    if status == "new":
        return "started"
    return status


async def create_and_log_session(
    prompt: str,
    issue_number: int,
    issue_title: str,
    db: Session,
) -> WebhookResponse:
    """Call the Devin API, persist a SessionLog, and return a response."""
    try:
        devin_response = await call_devin_api(
            "POST",
            f"/organizations/{settings.devin_org_id}/sessions",
            {"prompt": prompt},
        )
    except httpx.HTTPStatusError as exc:
        logger.error("Devin API error: %s - %s", exc.response.status_code, exc.response.text)
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
        status="started",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

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

    if x_github_event == "issue_comment":
        return await _handle_issue_comment(payload, db)

    if x_github_event == "issues":
        return await _handle_issue_opened(payload, db)

    return WebhookResponse(message=f"Ignored event: {x_github_event}")


async def _handle_issue_opened(payload: dict, db: Session) -> WebhookResponse:
    """Handle issues/opened events (original trigger)."""
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
    return await create_and_log_session(prompt, issue_number, issue_title, db)


async def _handle_issue_comment(payload: dict, db: Session) -> WebhookResponse:
    """Handle issue_comment/created events triggered by /devin commands."""
    action = payload.get("action")
    if action != "created":
        return WebhookResponse(message=f"Ignored action: {action}")

    comment_body = payload.get("comment", {}).get("body", "") or ""
    if not comment_body.startswith(TRIGGER_PREFIX):
        return WebhookResponse(message="Comment does not start with /devin, ignored")

    instructions = comment_body[len(TRIGGER_PREFIX):].strip()
    if not instructions:
        return WebhookResponse(message="No instructions after /devin, ignored")

    issue = payload.get("issue", {})
    issue_number = issue.get("number")
    issue_title = issue.get("title", "")
    issue_body = issue.get("body", "") or ""
    repo_full_name = payload.get("repository", {}).get("full_name", "")
    repo_url = payload.get("repository", {}).get("html_url", settings.target_repo_url)
    commenter = payload.get("comment", {}).get("user", {}).get("login", "unknown")

    prompt = (
        f"An engineer (@{commenter}) requested help on an issue in {repo_full_name} "
        f"via a /devin command.\n\n"
        f"Issue #{issue_number}: {issue_title}\n\n"
        f"Original issue description:\n{issue_body}\n\n"
        f"Instructions from the comment:\n{instructions}\n\n"
        f"Please:\n"
        f"1. Clone the repository: {repo_url}\n"
        f"2. Follow the instructions above to address the issue\n"
        f"3. Open a pull request with the fix, referencing issue #{issue_number}"
    )

    logger.info(
        "Creating Devin session from /devin comment by %s on issue #%s",
        commenter,
        issue_number,
    )
    return await create_and_log_session(prompt, issue_number, issue_title, db)


@app.get("/status", response_model=list[SessionLogResponse])
def get_status(db: Session = Depends(get_db)) -> list[SessionLogResponse]:
    """Return all session logs, newest first."""
    logs = db.query(SessionLog).order_by(SessionLog.created_at.desc()).all()
    return [SessionLogResponse.model_validate(log) for log in logs]


@app.get("/metrics", response_model=MetricsResponse)
def get_metrics(db: Session = Depends(get_db)) -> MetricsResponse:
    """
    Aggregated analytics for engineering leadership.

    Returns total sessions, breakdown by status, success rate,
    and how many sessions produced pull requests.
    """
    logs = db.query(SessionLog).all()
    total = len(logs)
    status_counts: dict[str, int] = dict(Counter(log.status for log in logs))
    completed = status_counts.get("completed", 0)
    failed = status_counts.get("failed", 0)
    decided = completed + failed
    success_rate = f"{(completed / decided * 100):.1f}%" if decided > 0 else "N/A (no completed sessions)"
    sessions_with_prs = sum(1 for log in logs if log.pull_request_url)

    latest = (
        db.query(SessionLog)
        .order_by(SessionLog.created_at.desc())
        .first()
    )

    return MetricsResponse(
        total_sessions=total,
        by_status=status_counts,
        success_rate=success_rate,
        sessions_with_prs=sessions_with_prs,
        latest_session=SessionLogResponse.model_validate(latest) if latest else None,
    )


@app.post("/sessions/refresh")
async def refresh_sessions(db: Session = Depends(get_db)) -> dict:
    """
    Poll the Devin API for each active session and update its status.

    This lets an operator (or a cron job) keep the local database
    in sync with Devin's actual progress without manual intervention.
    """
    active_logs = (
        db.query(SessionLog)
        .filter(SessionLog.status.in_(["started", "running", "blocked"]))
        .all()
    )

    if not active_logs:
        return {"updated": 0, "message": "No active sessions to refresh"}

    updated_count = 0
    errors: list[str] = []

    for log in active_logs:
        try:
            session_data = await call_devin_api(
                "GET",
                f"/organizations/{settings.devin_org_id}/sessions/{log.devin_session_id}",
            )
            new_status = map_devin_status(
                session_data.get("status", ""),
                session_data.get("status_detail"),
            )
            new_detail = session_data.get("status_detail")
            prs = session_data.get("pull_requests", [])
            pr_url = prs[0].get("url", "") if prs else None

            if log.status != new_status or log.pull_request_url != pr_url:
                log.status = new_status
                log.status_detail = new_detail
                if pr_url:
                    log.pull_request_url = pr_url
                log.updated_at = datetime.now(timezone.utc)
                updated_count += 1

                logger.info(
                    "Session %s updated: status=%s, pr=%s",
                    log.devin_session_id, new_status, pr_url,
                )

        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            errors.append(f"{log.devin_session_id}: {exc}")
            logger.warning("Failed to refresh session %s: %s", log.devin_session_id, exc)

    db.commit()

    return {
        "updated": updated_count,
        "checked": len(active_logs),
        "errors": errors,
    }


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
