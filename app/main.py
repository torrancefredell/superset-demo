import hashlib
import hmac
import logging

import httpx
from fastapi import FastAPI, Header, HTTPException, Request

from app.config import settings
from app.schemas import WebhookResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Superset Security Remediator",
    description=(
        "Event-driven automation that intercepts CodeQL code_scanning_alert "
        "webhooks and triggers Devin AI sessions to remediate vulnerabilities."
    ),
)


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


async def call_devin_api(prompt: str) -> dict:
    """POST a new Devin session with the given prompt."""
    url = f"{settings.devin_api_base_url}/organizations/{settings.devin_org_id}/sessions"
    headers = {
        "Authorization": f"Bearer {settings.devin_api_token}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json={"prompt": prompt}, headers=headers)
        response.raise_for_status()
        return response.json()


def build_remediation_prompt(
    rule_description: str,
    tool_name: str,
    file_path: str,
    alert_url: str,
    repo_url: str,
) -> str:
    return (
        "You are a DevSecOps automated remediation agent. "
        "A security vulnerability has been detected in our codebase via "
        f"{tool_name}.\n\n"
        f"Vulnerability Type: {rule_description}\n"
        f"Target File Location: {file_path}\n"
        f"Review Link: {alert_url}\n\n"
        f"Please:\n"
        f"1. Clone the repository: {repo_url}\n"
        f"2. Analyze the insecure code pattern inside the target file\n"
        f"3. Remediate the vulnerability safely according to modern "
        f"secure coding principles\n"
        f"4. Ensure the codebase builds and tests pass\n"
        f"5. Open a secure Pull Request referencing this automated remediation"
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/webhook", response_model=WebhookResponse)
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(None),
    x_hub_signature_256: str | None = Header(None),
) -> WebhookResponse:
    body = await request.body()

    if not verify_github_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()

    if x_github_event == "code_scanning_alert":
        return await _handle_code_scanning_alert(payload)

    return WebhookResponse(message=f"Ignored event: {x_github_event}")


async def _handle_code_scanning_alert(payload: dict) -> WebhookResponse:
    """Handle code_scanning_alert/created events from CodeQL."""
    action = payload.get("action")
    if action != "created":
        return WebhookResponse(message=f"Ignored action: {action}")

    alert = payload.get("alert", {})
    rule_description = alert.get("rule", {}).get("description", "Unknown vulnerability")
    alert_url = alert.get("html_url", "")
    file_path = (
        alert.get("most_recent_instance", {})
        .get("location", {})
        .get("path", "unknown")
    )
    tool_name = payload.get("tool", {}).get("name", "CodeQL")
    repo_url = payload.get("repository", {}).get("html_url", settings.target_repo_url)

    prompt = build_remediation_prompt(
        rule_description=rule_description,
        tool_name=tool_name,
        file_path=file_path,
        alert_url=alert_url,
        repo_url=repo_url,
    )

    logger.info(
        "Creating Devin session for CodeQL alert: %s in %s",
        rule_description,
        file_path,
    )

    try:
        devin_response = await call_devin_api(prompt)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Devin API error: %s - %s",
            exc.response.status_code,
            exc.response.text,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Devin API returned {exc.response.status_code}",
        ) from exc
    except httpx.RequestError as exc:
        logger.error("Devin API request failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to reach Devin API",
        ) from exc

    devin_session_id = devin_response.get("devin_id", "")
    devin_session_url = devin_response.get("url", "")

    logger.info("Devin session created: %s", devin_session_id)

    return WebhookResponse(
        message="Devin remediation session created",
        devin_session_id=devin_session_id,
        devin_session_url=devin_session_url,
        alert_url=alert_url,
        rule_description=rule_description,
        file_path=file_path,
    )


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
