# Superset Issue Automator

An event-driven automation system that watches a GitHub repository for new issues and dispatches [Devin](https://devin.ai) AI sessions to analyze, fix, and open pull requests — without human intervention.

Built for the [Apache Superset](https://github.com/apache/superset) fork at [`torrancefredell/superset`](https://github.com/torrancefredell/superset).

---

## Why an AI Agent Instead of a CI/CD Script?

Traditional CI/CD pipelines excel at deterministic tasks: run tests, build artifacts, deploy. But they fall short when the fix itself requires judgment:

| Dimension | CI/CD Script | AI Agent (Devin) |
|---|---|---|
| **Scope of action** | Runs a predefined sequence of commands | Reads code, reasons about context, writes a novel fix |
| **Handling ambiguity** | Fails or skips when the fix isn't obvious | Interprets issue descriptions in natural language |
| **Cross-file fixes** | Requires hand-authored regex or AST transforms | Navigates the codebase and edits multiple files |
| **Dependency upgrades** | Can bump versions, but can't verify compatibility | Bumps the version, runs the test suite, and adjusts code if something breaks |
| **Security remediations** | Can flag a finding; cannot author the patch | Reads the advisory, applies the safe alternative, and removes suppressions |

For the three issue categories selected in this project — outdated dependencies, unused imports, and unsafe YAML loading — an AI agent treats each issue as a small engineering task rather than a string-replacement job. This approach generalizes to any issue that can be described in a GitHub issue body.

---

## Architecture

```
┌─────────────┐       webhook (POST)       ┌──────────────────────┐
│   GitHub     │ ─────────────────────────▸ │  FastAPI App         │
│   Issues     │                            │                      │
└─────────────┘                            │  /webhook            │
                                            │  /status             │
                                            │  /metrics            │
                                            │  /sessions/refresh   │
                                            │  /health             │
                                            └──────┬───────────────┘
                                                   │
                                    Devin API       │       SQLite
                                  (POST session)    │    (session logs)
                                                   │
                                            ┌──────▼───────────────┐
                                            │  Devin AI            │
                                            │  - clones repo       │
                                            │  - analyzes issue    │
                                            │  - opens PR          │
                                            └──────────────────────┘
```

### How It Maps to the Challenge Requirements

| Requirement | How This Project Satisfies It |
|---|---|
| **Part 2 — Event trigger** | GitHub webhook fires on `issues.opened` events and `issue_comment.created` events containing a `/devin` command → `POST /webhook` |
| **Part 2 — Programmatic session management** | The app calls `POST /v3/organizations/{org_id}/sessions` with a structured prompt containing the issue title, description, and repo URL |
| **Part 2 — Observable outputs** | Devin creates pull requests that close the original issues; PRs are visible in the fork |
| **Part 3 — Status of tasks** | `GET /status` returns every session with its current state (`started`, `running`, `completed`, `failed`, `blocked`) |
| **Part 3 — Success/failure signals** | `POST /sessions/refresh` polls the Devin API and updates each session's status and linked PR in the local database |
| **Part 3 — Throughput / progress** | `GET /metrics` returns aggregated analytics: total sessions, breakdown by status, success rate, and count of sessions that produced PRs |
| **Deliverable — Docker** | `Dockerfile` + `docker-compose.yml` with a single `docker compose up --build` command |
| **Deliverable — Clear README** | This document |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/webhook` | Receives GitHub webhook payloads. Handles `issues`/`opened` events and `issue_comment`/`created` events with a `/devin` trigger. Validates HMAC-SHA256 signature, creates a Devin session, and logs it. |
| `GET` | `/status` | Returns all session logs as JSON (newest first). Each entry includes issue number, Devin session ID, status, PR URL, and timestamps. |
| `GET` | `/metrics` | Aggregated dashboard: total sessions, status breakdown, success rate, sessions with PRs, and the latest session. |
| `POST` | `/sessions/refresh` | Polls the Devin API for every active session and syncs status + PR URLs back to the local database. |
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

The app starts at **http://localhost:8000**. The SQLite database is persisted in a Docker volume (`db-data`), so data survives container restarts.

### 4. Verify

```bash
# Health check
curl http://localhost:8000/health
# → {"status":"ok"}

# View session logs (empty on first run)
curl http://localhost:8000/status
# → []

# View metrics
curl http://localhost:8000/metrics
```

### 5. Simulate a webhook (without configuring GitHub)

You can test the full flow locally by sending a simulated GitHub webhook payload:

```bash
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: issues" \
  -d '{
    "action": "opened",
    "issue": {
      "number": 1,
      "title": "Bump pandas from 2.1.4 to 2.3.x in requirements/base.txt",
      "body": "The pandas dependency is pinned at 2.1.4. Please update to 2.3.3."
    },
    "repository": {
      "full_name": "torrancefredell/superset",
      "html_url": "https://github.com/torrancefredell/superset"
    }
  }'
```

You can also trigger a session via a simulated issue comment with the `/devin` prefix:

```bash
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: issue_comment" \
  -d '{
    "action": "created",
    "comment": {
      "body": "/devin Please fix this by updating the pinned version to 2.3.3",
      "user": { "login": "torrancefredell" }
    },
    "issue": {
      "number": 1,
      "title": "Bump pandas from 2.1.4 to 2.3.x in requirements/base.txt",
      "body": "The pandas dependency is pinned at 2.1.4. Please update to 2.3.3."
    },
    "repository": {
      "full_name": "torrancefredell/superset",
      "html_url": "https://github.com/torrancefredell/superset"
    }
  }'
```

Then check the results:

```bash
# See the logged session
curl http://localhost:8000/status | python3 -m json.tool

# Refresh session status from Devin API
curl -X POST http://localhost:8000/sessions/refresh

# View aggregated metrics
curl http://localhost:8000/metrics | python3 -m json.tool
```

### Stop the app

```bash
docker compose down        # stop containers (data persists)
docker compose down -v     # stop and delete the database volume
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
| `TARGET_REPO_URL` | No | `https://github.com/torrancefredell/superset` | Fallback repository URL if not present in the webhook payload. |
| `DATABASE_URL` | No | `sqlite:///./devin_sessions.db` | SQLAlchemy connection string. Docker Compose overrides this to use a persistent volume. |
| `DEVIN_API_BASE_URL` | No | `https://api.devin.ai/v3` | Override for local development or testing with a mock server. |

---

## Configuring the GitHub Webhook

To connect this to a real repository:

1. Go to your repo's **Settings → Webhooks → Add webhook**
2. **Payload URL**: Your server's public URL + `/webhook` (e.g., `https://your-server.com/webhook`)
3. **Content type**: `application/json`
4. **Secret**: Same value as `GITHUB_WEBHOOK_SECRET` in your `.env`
5. **Events**: Select **Issues** and **Issue comments**

For local development, use [ngrok](https://ngrok.com) to expose your local server:

```bash
ngrok http 8000
# Use the HTTPS URL from ngrok as your Payload URL
```

---

## Observability

### `GET /status` — Session Log

Returns every Devin session triggered by this system:

```json
[
  {
    "id": 1,
    "github_issue_number": 1,
    "github_issue_title": "Bump pandas from 2.1.4 to 2.3.x",
    "devin_session_id": "devin-abc123",
    "devin_session_url": "https://app.devin.ai/sessions/abc123",
    "status": "completed",
    "status_detail": "finished",
    "pull_request_url": "https://github.com/torrancefredell/superset/pull/4",
    "created_at": "2026-05-28T01:00:00",
    "updated_at": "2026-05-28T01:15:00"
  }
]
```

### `GET /metrics` — Engineering Dashboard

Answers the question: *"If I were an engineering leader, how would I know this is working?"*

```json
{
  "total_sessions": 3,
  "by_status": {
    "completed": 2,
    "running": 1
  },
  "success_rate": "100.0%",
  "sessions_with_prs": 2,
  "latest_session": { "..." }
}
```

### `POST /sessions/refresh` — Sync with Devin

Polls the Devin API for all active sessions and updates their status and PR links in the local database. Call this manually or wire it to a cron job:

```bash
curl -X POST http://localhost:8000/sessions/refresh
# → {"updated": 1, "checked": 2, "errors": []}
```

---

## Project Structure

```
superset-demo/
├── app/
│   ├── __init__.py
│   ├── config.py          # Pydantic settings (loads .env)
│   ├── database.py        # SQLAlchemy engine and session factory
│   ├── main.py            # FastAPI app — all endpoints
│   ├── models.py          # SessionLog ORM model
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
| [`torrancefredell/superset`](https://github.com/torrancefredell/superset) | Fork of Apache Superset with the issues to be remediated |
