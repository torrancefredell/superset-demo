---
name: testing-issue-automator
description: Test the FastAPI issue automator app end-to-end. Use when verifying webhook, status, or Devin API integration changes.
---

# Testing the Superset Issue Automator

## Prerequisites

- Python 3.10+
- Dependencies installed: `pip install -r requirements.txt`

## Devin Secrets Needed

For full integration testing with the real Devin API:
- `DEVIN_API_TOKEN` — Devin service user API token
- `DEVIN_ORG_ID` — Devin organization ID

For local testing, these can be replaced with a mock server (see below).

## Running the App Locally

```bash
cd /home/ubuntu/repos/superset-demo
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The SQLite database (`devin_sessions.db`) is created automatically.

## Testing Without Real Devin API Credentials

Spin up a mock HTTP server that returns canned Devin API responses:

```python
# mock_devin_api.py
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

LOG_FILE = "/tmp/mock_requests.json"

class MockDevinHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        req_data = {
            "path": self.path,
            "auth": self.headers.get("Authorization"),
            "body": json.loads(body) if body else None,
        }
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(req_data) + "\n")
        response = json.dumps({"devin_id": "devin-mock123", "url": "https://app.devin.ai/sessions/mock123"})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(response.encode())
    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    import os
    if os.path.exists(LOG_FILE): os.remove(LOG_FILE)
    HTTPServer(("0.0.0.0", 9999), MockDevinHandler).serve_forever()
```

Start mock: `python mock_devin_api.py &`

Start app pointing at mock:
```bash
DEVIN_API_BASE_URL=http://localhost:9999/v3 \
DEVIN_API_TOKEN=test-token \
DEVIN_ORG_ID=org-test \
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Key Test Scenarios

### 1. Health check
```bash
curl http://localhost:8000/health
# Expected: {"status":"ok"} HTTP 200
```

### 2. Empty status
```bash
curl http://localhost:8000/status
# Expected: [] HTTP 200
```

### 3. Event filtering
```bash
# Non-issue events are ignored
curl -X POST http://localhost:8000/webhook -H "Content-Type: application/json" -H "X-GitHub-Event: ping" -d '{"zen":"test"}'
# Expected: {"message":"Ignored event: ping",...}

# Non-opened actions are ignored
curl -X POST http://localhost:8000/webhook -H "Content-Type: application/json" -H "X-GitHub-Event: issues" -d '{"action":"closed",...}'
# Expected: {"message":"Ignored action: closed",...}
```

### 4. Happy path (with mock)
```bash
curl -X POST http://localhost:8000/webhook -H "Content-Type: application/json" -H "X-GitHub-Event: issues" \
  -d '{"action":"opened","issue":{"number":42,"title":"Test","body":"desc"},"repository":{"full_name":"t/r","html_url":"https://github.com/t/r"}}'
# Expected: {"message":"Devin session created","devin_session_id":"devin-mock123","github_issue_number":42}
# Then GET /status should show the logged entry
```

### 5. Error handling
```bash
# Point DEVIN_API_BASE_URL at a dead port to test 502
# Expected: {"detail":"Failed to reach Devin API"} HTTP 502
```

### 6. Signature verification
```bash
# Set GITHUB_WEBHOOK_SECRET=testsecret123
# Send with invalid X-Hub-Signature-256 header
# Expected: {"detail":"Invalid signature"} HTTP 401

# Compute valid signature:
BODY='{...}'
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "testsecret123" | awk '{print $2}')
# Send with X-Hub-Signature-256: sha256=$SIG
# Expected: HTTP 200
```

### 7. Validate Devin API request
Check `/tmp/mock_requests.json` to verify:
- Path contains `/v3/organizations/{org_id}/sessions`
- Auth header is `Bearer {token}`
- Body prompt contains issue number, title, description, and repo URL

## Notes

- This is a shell-only API app — no browser UI, so no screen recording needed
- Delete `devin_sessions.db` between test runs for a clean state
- The app uses Pydantic Settings with `.env` file support — env vars override `.env`
