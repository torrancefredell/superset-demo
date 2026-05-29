# Superset Security Remediator

An event-driven automation system that intercepts [CodeQL](https://codeql.github.com/) `code_scanning_alert` webhooks from GitHub and dispatches [Devin](https://devin.ai) AI sessions to remediate security vulnerabilities — without human intervention.

Built for the [Apache Superset](https://github.com/apache/superset) fork at [`torrancefredell/superset`](https://github.com/torrancefredell/superset).

---

## Why an AI Agent Instead of a CI/CD Script?

Traditional CI/CD pipelines excel at deterministic tasks: run tests, build artifacts, deploy. But they fall short when the fix itself requires judgment:

| Dimension | CI/CD Script | AI Agent (Devin) |
|---|---|---|
| **Scope of action** | Runs a predefined sequence of commands | Reads code, reasons about context, writes a novel fix |
| **Handling ambiguity** | Fails or skips when the fix isn't obvious | Interprets vulnerability descriptions in natural language |
| **Cross-file fixes** | Requires hand-authored regex or AST transforms | Navigates the codebase and edits multiple files |
| **Security remediations** | Can flag a finding; cannot author the patch | Reads the advisory, applies the safe alternative, and removes suppressions |

By connecting CodeQL scanning directly to an AI agent, every newly discovered vulnerability triggers an autonomous remediation cycle — from detection to pull request.

---

## Architecture

```
┌─────────────┐    code_scanning_alert     ┌──────────────────────┐
│   GitHub     │    webhook (POST)          │  FastAPI App         │
│   CodeQL     │ ─────────────────────────▸ │                      │
│   Scanning   │                            │  /webhook            │
└─────────────┘                            │  /health             │
                                            └──────┬───────────────┘
                                                   │
                                        ┌──────────▼──────────┐
                                        │ Duplicate PR Check  │
                                        │ (GitHub API)        │
                                        └──────────┬──────────┘
                                                   │
                                    ┌──────────────┼──────────────┐
                                    │ No match     │ Match found  │
                                    ▼              ▼              │
                            ┌──────────────┐ ┌──────────────┐    │
                            │ New PR path  │ │ Update path  │    │
                            │ Create fresh │ │ Push to      │    │
                            │ branch + PR  │ │ existing     │    │
                            └──────┬───────┘ │ branch       │    │
                                   │         └──────┬───────┘    │
                                   └────────────────┘            │
                                            │                    │
                                    Devin API                    │
                                  (POST session)                 │
                                            │                    │
                                    ┌───────▼──────────────┐     │
                                    │  Devin AI            │     │
                                    │  - clones repo       │     │
                                    │  - analyzes vuln     │     │
                                    │  - remediates code   │     │
                                    │  - opens/updates PR  │     │
                                    └──────────────────────┘     │
```

### Deduplication via Alert Tags

When the gateway processes a new `code_scanning_alert`, it checks for duplicate PRs before dispatching:

1. **Tag injection**: New PRs include a hidden HTML tag at the bottom of the description: `<!-- CODEQL_ALERT:N -->` (where N is the CodeQL alert number).
2. **Lookup**: On each webhook, the gateway fetches open PRs via the GitHub API and searches their body text for the matching alert tag.
3. **Two execution paths**:
   - **No match found** → Create a fresh branch and open a new PR.
   - **Match found** → Dispatch Devin to push commits to the existing branch, updating the fix in-place without opening a duplicate PR.

This prevents duplicate PRs from spawning when webhooks are redelivered or alerts are reopened.

> **Note**: Deduplication requires `GITHUB_TOKEN` to be set. Without it, the gateway logs a warning and always creates a new PR.

### How It Maps to the Challenge Requirements

| Requirement | How This Project Satisfies It |
|---|---|
| **Part 2 — Event trigger** | GitHub webhook fires on `code_scanning_alert` events (`created` or `reopened_by_user`) from CodeQL → `POST /webhook` |
| **Part 2 — Programmatic session management** | The app calls `POST /v3/organizations/{org_id}/sessions` with a structured DevSecOps prompt containing the vulnerability type, file path, and alert URL |
| **Part 2 — Observable outputs** | Devin creates pull requests that remediate the detected vulnerabilities; PRs are visible in the fork |
| **Deliverable — Docker** | `Dockerfile` + `docker-compose.yml` with a single `docker compose up --build` command |
| **Deliverable — Clear README** | This document |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/webhook` | Receives GitHub webhook payloads. Handles `code_scanning_alert` events (`created` and `reopened_by_user` actions), validates HMAC-SHA256 signature, extracts vulnerability details, and creates a Devin remediation session. |
| `GET` | `/health` | Returns `{"status": "ok"}`. Used by Docker healthcheck. |

---

## Quick Start (Docker)

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose installed
- A Devin API token and organization ID ([get them here](https://app.devin.ai/settings/service-users))

### 1. Clone the repository

```bash
git clone https://github.com/torrancefredell/superset-demo.git
cd superset-demo
```

### 2. Create your `.env` file

```bash
cp .env.example .env
```

Open `.env` and fill in the two required values:

```env
DEVIN_API_TOKEN=your_devin_api_token_here
DEVIN_ORG_ID=your_devin_org_id_here
```

### 3. Build and run

```bash
docker compose up --build
```

The app starts at **http://localhost:8000**.

### 4. Verify

```bash
curl http://localhost:8000/health
# → {"status":"ok"}
```

### 5. Simulate a CodeQL webhook (without configuring GitHub)

You can test the full flow locally by sending a simulated `code_scanning_alert` payload:

```bash
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: code_scanning_alert" \
  -d '{
    "action": "created",
    "alert": {
      "rule": {
        "description": "Use of unsafe yaml.Loader allows arbitrary code execution"
      },
      "html_url": "https://github.com/torrancefredell/superset/security/code-scanning/1",
      "most_recent_instance": {
        "location": {
          "path": "superset/examples/utils.py"
        }
      }
    },
    "tool": {
      "name": "CodeQL"
    },
    "repository": {
      "html_url": "https://github.com/torrancefredell/superset"
    }
  }'
```

Expected response:

```json
{
  "message": "Devin remediation session created",
  "devin_session_id": "devin-...",
  "devin_session_url": "https://app.devin.ai/sessions/...",
  "alert_url": "https://github.com/torrancefredell/superset/security/code-scanning/1",
  "rule_description": "Use of unsafe yaml.Loader allows arbitrary code execution",
  "file_path": "superset/examples/utils.py"
}
```

### Stop the app

```bash
docker compose down
```

---

## Alternative: Run Without Docker

```bash
pip install -r requirements.txt
cp .env.example .env       # fill in DEVIN_API_TOKEN and DEVIN_ORG_ID
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DEVIN_API_TOKEN` | **Yes** | — | Bearer token for authenticating with the Devin API. Create a service user at [app.devin.ai/settings/service-users](https://app.devin.ai/settings/service-users) and generate an API key. |
| `DEVIN_ORG_ID` | **Yes** | — | Your Devin organization ID (the `org-...` value on the Service Users page). |
| `GITHUB_WEBHOOK_SECRET` | No | *(empty)* | When set, the app validates incoming webhooks using HMAC-SHA256. Generate one: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `GITHUB_TOKEN` | No | *(empty)* | GitHub personal access token with `repo` scope. Required for duplicate PR detection. [Create one here](https://github.com/settings/tokens). |
| `TARGET_REPO_URL` | No | `https://github.com/torrancefredell/superset` | Fallback repository URL if not present in the webhook payload. |
| `DEVIN_API_BASE_URL` | No | `https://api.devin.ai/v3` | Override for local development or testing with a mock server. |

---

## Configuring the GitHub Webhook

To connect this to a real repository with CodeQL enabled:

1. Go to your repo's **Settings → Webhooks → Add webhook**
2. **Payload URL**: Your server's public URL + `/webhook` (e.g., `https://your-server.com/webhook`)
3. **Content type**: `application/json`
4. **Secret**: Same value as `GITHUB_WEBHOOK_SECRET` in your `.env`
5. **Events**: Select **Code scanning alerts**

For local development, use [ngrok](https://ngrok.com) to expose your local server:

```bash
ngrok http 8000
# Use the HTTPS URL from ngrok as your Payload URL
```

---

## DevSecOps Prompt

When a `code_scanning_alert` with `action: "created"` or `action: "reopened_by_user"` arrives, the app constructs a structured prompt for the Devin session:

```
You are a DevSecOps automated remediation agent. A security vulnerability
has been detected in our codebase via CodeQL.

Vulnerability Type: [Rule Description]
Target File Location: [File Path]
Review Link: [Alert HTML URL]

Please:
1. Clone the repository
2. Analyze the insecure code pattern inside the target file
3. Remediate the vulnerability safely according to modern secure coding principles
4. Ensure the codebase builds and tests pass
5. Open a Pull Request with the exact title: 'Fix: [Rule Description]'
6. Include <!-- CODEQL_ALERT:N --> at the bottom of the PR body
```

If an existing open PR already addresses the same alert, the prompt instructs Devin to push to the existing branch instead of opening a new PR.

---

## Project Structure

```
superset-demo/
├── app/
│   ├── __init__.py
│   ├── config.py          # Pydantic settings (loads .env)
│   ├── main.py            # FastAPI app — webhook + health endpoints
│   └── schemas.py         # Pydantic response schemas
├── .dockerignore
├── .env.example           # Template for required environment variables
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## Related Repositories

| Repository | Purpose |
|---|---|
| [`torrancefredell/superset-demo`](https://github.com/torrancefredell/superset-demo) | This automation system (you are here) |
| [`torrancefredell/superset`](https://github.com/torrancefredell/superset) | Fork of Apache Superset with CodeQL scanning enabled |
