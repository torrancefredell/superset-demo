import hashlib
import hmac
import logging
import re

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

_ALERT_TAG_RE = re.compile(r"<!-- CODEQL_ALERT:(\d+) -->")


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


async def find_existing_pr_for_alert(
    repo_full_name: str,
    alert_number: int,
) -> dict | None:
    """Search open PRs for one whose body contains <!-- CODEQL_ALERT:N -->."""
    if not settings.github_token:
        logger.warning(
            "GITHUB_TOKEN not set — skipping duplicate PR check for alert #%s",
            alert_number,
        )
        return None

    api_url = f"https://api.github.com/repos/{repo_full_name}/pulls"
    headers = {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
    }
    tag = f"<!-- CODEQL_ALERT:{alert_number} -->"

    async with httpx.AsyncClient(timeout=15.0) as client:
        page = 1
        while True:
            resp = await client.get(
                api_url,
                headers=headers,
                params={"state": "open", "per_page": 100, "page": page},
            )
            resp.raise_for_status()
            prs = resp.json()
            if not prs:
                break
            for pr in prs:
                body = pr.get("body") or ""
                if tag in body:
                    return {
                        "number": pr["number"],
                        "branch": pr["head"]["ref"],
                        "html_url": pr["html_url"],
                    }
            page += 1

    return None


def build_new_pr_prompt(
    rule_description: str,
    tool_name: str,
    file_path: str,
    alert_url: str,
    alert_number: int,
    repo_url: str,
) -> str:
    return (
        "You are a DevSecOps automated remediation agent. "
        "A security vulnerability has been detected in our codebase via "
        f"{tool_name}.\n\n"
        f"Vulnerability Type: {rule_description}\n"
        f"Target File Location: {file_path}\n"
        f"Review Link: {alert_url}\n\n"
        "Please:\n"
        f"1. Clone the repository: {repo_url}\n"
        "2. Analyze the insecure code pattern inside the target file\n"
        "3. Remediate the vulnerability safely according to modern "
        "secure coding principles\n"
        "4. Ensure the codebase builds and tests pass\n"
        "5. Open a Pull Request with the exact title: "
        f"'Fix: {rule_description}'\n"
        "6. At the very bottom of the Pull Request description body, "
        "include this exact hidden HTML tag on its own line:\n"
        f"   <!-- CODEQL_ALERT:{alert_number} -->"
    )


def build_update_pr_prompt(
    rule_description: str,
    tool_name: str,
    file_path: str,
    alert_url: str,
    existing_branch: str,
    existing_pr_number: int,
    repo_url: str,
) -> str:
    return (
        "You are a DevSecOps automated remediation agent. "
        "A security vulnerability has been re-detected or reopened in our "
        f"codebase via {tool_name}.\n\n"
        f"Vulnerability Type: {rule_description}\n"
        f"Target File Location: {file_path}\n"
        f"Review Link: {alert_url}\n\n"
        f"An existing Pull Request (#{existing_pr_number}) already addresses "
        f"this alert on branch '{existing_branch}'.\n\n"
        "Please:\n"
        f"1. Clone the repository: {repo_url}\n"
        f"2. Check out the existing branch: {existing_branch}\n"
        "3. Analyze the insecure code pattern inside the target file\n"
        "4. Update or improve the fix on this branch\n"
        "5. Ensure the codebase builds and tests pass\n"
        "6. Push your commits to the existing branch — do NOT open a new PR\n"
        "7. Keep the PR title as: "
        f"'Fix: {rule_description}'"
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


_ACTIONABLE = {"created", "reopened_by_user"}


async def _handle_code_scanning_alert(payload: dict) -> WebhookResponse:
    """Handle code_scanning_alert events from CodeQL."""
    action = payload.get("action")
    if action not in _ACTIONABLE:
        return WebhookResponse(message=f"Ignored action: {action}")

    alert = payload.get("alert", {})
    rule_description = alert.get("rule", {}).get("description", "Unknown vulnerability")
    alert_url = alert.get("html_url", "")
    alert_number = alert.get("number")
    file_path = (
        alert.get("most_recent_instance", {})
        .get("location", {})
        .get("path", "unknown")
    )
    tool_name = alert.get("tool", {}).get("name", "CodeQL")
    repo = payload.get("repository", {})
    repo_url = repo.get("html_url", settings.target_repo_url)
    repo_full_name = repo.get("full_name", "")

    # --- Deduplication: check for an existing open PR for this alert ---
    existing_pr = None
    if alert_number is not None and repo_full_name:
        try:
            existing_pr = await find_existing_pr_for_alert(
                repo_full_name, alert_number
            )
        except httpx.HTTPError as exc:
            logger.warning(
                "GitHub API check failed for alert #%s, proceeding with new PR: %s",
                alert_number,
                exc,
            )

    if existing_pr:
        logger.info(
            "Found existing PR #%s on branch '%s' for alert #%s — dispatching update",
            existing_pr["number"],
            existing_pr["branch"],
            alert_number,
        )
        prompt = build_update_pr_prompt(
            rule_description=rule_description,
            tool_name=tool_name,
            file_path=file_path,
            alert_url=alert_url,
            existing_branch=existing_pr["branch"],
            existing_pr_number=existing_pr["number"],
            repo_url=repo_url,
        )
    else:
        logger.info(
            "No existing PR for alert #%s — creating new remediation session: %s in %s",
            alert_number,
            rule_description,
            file_path,
        )
        prompt = build_new_pr_prompt(
            rule_description=rule_description,
            tool_name=tool_name,
            file_path=file_path,
            alert_url=alert_url,
            alert_number=alert_number,
            repo_url=repo_url,
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

    if existing_pr:
        msg = (
            f"Devin session dispatched to update existing PR #{existing_pr['number']}"
        )
    else:
        msg = "Devin remediation session created"

    logger.info("Devin session created: %s", devin_session_id)

    return WebhookResponse(
        message=msg,
        devin_session_id=devin_session_id,
        devin_session_url=devin_session_url,
        alert_url=alert_url,
        rule_description=rule_description,
        file_path=file_path,
    )


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
