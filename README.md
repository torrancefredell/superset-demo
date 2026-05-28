# Superset Issue Automator

A FastAPI app that listens for GitHub **issue created** webhook events and automatically triggers [Devin](https://devin.ai) sessions to analyze and fix them.

## How It Works

1. A new issue is created in your GitHub repository.
2. GitHub sends a webhook payload to the `/webhook` endpoint.
3. The app extracts the issue title and description, then calls the Devin API to start a new session with a prompt that asks Devin to clone the repo, fix the issue, and open a PR.
4. The session is logged to a local SQLite database with the GitHub issue number, Devin session ID, timestamp, and status.
5. Engineering leaders can view throughput via the `GET /status` endpoint.

## Endpoints

| Method | Path       | Description                                      |
|--------|------------|--------------------------------------------------|
| POST   | `/webhook` | Receives GitHub webhook payloads (issue events)   |
| GET    | `/status`  | Returns all Devin session logs (JSON)             |
| GET    | `/health`  | Simple health check                               |

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment variables

Create a `.env` file in the project root:

```env
DEVIN_API_TOKEN=your_devin_api_token
DEVIN_ORG_ID=your_devin_org_id
GITHUB_WEBHOOK_SECRET=your_github_webhook_secret
TARGET_REPO_URL=https://github.com/torrancefredell/superset
```

| Variable               | Required | Description                                              |
|------------------------|----------|----------------------------------------------------------|
| `DEVIN_API_TOKEN`      | Yes      | API token for authenticating with the Devin API           |
| `DEVIN_ORG_ID`         | Yes      | Your Devin organization ID                                |
| `GITHUB_WEBHOOK_SECRET`| No       | Secret for validating GitHub webhook signatures           |
| `TARGET_REPO_URL`      | No       | Fallback repo URL if not present in the webhook payload   |

### 3. Run the server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The SQLite database (`devin_sessions.db`) is created automatically on first run.

### 4. Configure the GitHub webhook

In your GitHub repository, go to **Settings → Webhooks → Add webhook**:

- **Payload URL**: `https://your-server.com/webhook`
- **Content type**: `application/json`
- **Secret**: Same value as `GITHUB_WEBHOOK_SECRET`
- **Events**: Select **Issues**

## Viewing Session Logs

```bash
curl http://localhost:8000/status | python -m json.tool
```

Example response:

```json
[
  {
    "id": 1,
    "github_issue_number": 42,
    "github_issue_title": "Bump pandas from 2.1.4 to 2.3.x",
    "devin_session_id": "devin-abc123",
    "devin_session_url": "https://app.devin.ai/sessions/abc123",
    "status": "Started",
    "created_at": "2026-05-28T01:00:00Z"
  }
]
```
