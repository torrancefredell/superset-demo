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

---

## Quick Start (Docker)

### 1. Clone the repository

```bash
git clone https://github.com/torrancefredell/superset-demo.git
cd superset-demo
```

### 2. Configure environment variables

Copy the example env file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
DEVIN_API_TOKEN=your_devin_api_token_here
DEVIN_ORG_ID=your_devin_org_id_here
GITHUB_WEBHOOK_SECRET=optional_webhook_secret
TARGET_REPO_URL=https://github.com/torrancefredell/superset
```

### 3. Run with Docker Compose

```bash
docker compose up --build
```

The app will be available at `http://localhost:8000`. The SQLite database is persisted in a Docker volume (`db-data`).

### 4. Verify it's running

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

### Stop the app

```bash
docker compose down
```

To also remove the database volume:

```bash
docker compose down -v
```

---

## Alternative: Run Without Docker

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy and edit the example env file:

```bash
cp .env.example .env
# Edit .env with your values
```

### 3. Run the server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The SQLite database (`devin_sessions.db`) is created automatically on first run.

---

## Environment Variables

| Variable               | Required | Default                                         | Description                                              |
|------------------------|----------|-------------------------------------------------|----------------------------------------------------------|
| `DEVIN_API_TOKEN`      | **Yes**  | —                                               | API token for authenticating with the Devin API. Get this from your Devin [Service Users](https://app.devin.ai/settings/service-users) page. |
| `DEVIN_ORG_ID`         | **Yes**  | —                                               | Your Devin organization ID. Found on the same Service Users page. |
| `GITHUB_WEBHOOK_SECRET`| No       | *(empty — signature verification skipped)*      | Secret for validating GitHub webhook signatures (HMAC-SHA256). Generate one with `python -c "import secrets; print(secrets.token_hex(32))"`. |
| `TARGET_REPO_URL`      | No       | `https://github.com/torrancefredell/superset`   | Fallback repo URL if not present in the webhook payload. |
| `DATABASE_URL`         | No       | `sqlite:///./devin_sessions.db`                 | SQLAlchemy connection string. The Docker setup overrides this to persist data in a volume. |
| `DEVIN_API_BASE_URL`   | No       | `https://api.devin.ai/v3`                       | Base URL for the Devin API. Override for testing with a mock server. |

### Where to find your Devin credentials

1. Go to [app.devin.ai](https://app.devin.ai) → **Settings** → **Service Users**.
2. Create a service user (or use an existing one).
3. Generate an API key — this is your `DEVIN_API_TOKEN`.
4. Your `DEVIN_ORG_ID` is shown on the same page (the `org-...` value).

---

## Configure the GitHub Webhook

In your GitHub repository, go to **Settings → Webhooks → Add webhook**:

- **Payload URL**: `https://your-server.com/webhook`
- **Content type**: `application/json`
- **Secret**: Same value as `GITHUB_WEBHOOK_SECRET` (leave blank if not using signature verification)
- **Events**: Select **Issues**

For local development, use a tunnel like [ngrok](https://ngrok.com) to expose your local server:

```bash
ngrok http 8000
# Use the ngrok URL as your Payload URL
```

---

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

---

## Project Structure

```
superset-demo/
├── app/
│   ├── __init__.py
│   ├── config.py       # Pydantic settings (env vars)
│   ├── database.py     # SQLAlchemy engine and session
│   ├── main.py         # FastAPI app with all endpoints
│   ├── models.py       # SessionLog ORM model
│   └── schemas.py      # Pydantic response schemas
├── .env.example        # Example environment variables
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```
