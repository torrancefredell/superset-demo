# Live Demo Walkthrough — Tactical Click-by-Click

**Presenter:** Torrance Fredell
**Segment:** The live demo (middle of the presentation, ~2:00 – 3:30)
**Goal:** Show the pipeline firing end to end — from a stale security backlog to a clean, human-ready Pull Request — without touching a line of code on stage.

> **Pre-flight checklist (do this before you hit record):**
> - Terminal is already running `docker compose up --build`; the gateway is healthy (`curl localhost:8000/health` → `{"status":"ok"}`).
> - Browser tabs open and ordered: **(1)** GitHub Code Scanning alerts, **(2)** a specific alert's *Webhook deliveries* view, **(3)** the repo's Pull Requests tab, **(4)** the Devin dashboard (`app.devin.ai`).
> - A second terminal pane ready with `docker compose logs -f` so the log stream is visible the instant you switch to it.
> - Zoom your browser to ~125% so the back row can read alert titles and PR names.

---

## Step 1 — The Security Backlog *(The Setup)*

**Visual:** GitHub → the Apache Superset fork → **Security → Code scanning** alerts dashboard.

**Action:**
1. Land on the open alerts list.
2. Slowly scroll the list top to bottom so the volume registers.
3. Hover on one representative finding — e.g. *Clear-text logging of sensitive information* — but don't click in yet.

**What to look for on screen:**
- The **Open** filter is active and the alert count is visible.
- A mix of rule types and a few alerts with old "first detected" dates.

**Narrative (say this):**
> "I don't need to explain this screen to you — you already live it. Every one of you has a queue that looks exactly like this in your own org, and the fact that it exists is proof your investment in CodeQL is working. Your scanners are doing their job: they find the bugs. Here's the quiet part nobody says out loud — finding is where most security tooling stops. It surfaces the vulnerability and then hands it back to a human, so these alerts just sit, aging for weeks, sometimes months. And the reason they sit is a tradeoff you make every single day: the only way to clear one is to pull a senior developer off a high-value feature, and the instant you do that, your product roadmap stalls. So we're not here to replace any of this. We're not swapping out CodeQL or your security stack. We're adding the layer that sits *on top* of it — the one that finally drains this backlog. Let me show you what that looks like the moment an alert fires."

---

## Step 2 — The Catalyst *(The Retrigger Event)*

**Visual:** Drill into a single alert, then surface the webhook that powers it.

**Action:**
1. Click into one specific alert to show the advisory detail (rule, file, line).
2. Switch to repo **Settings → Webhooks**, open the gateway's webhook, and select the **Recent Deliveries** tab.
3. Pick a `code_scanning_alert` delivery and click **Redeliver** → confirm.

**What to look for on screen:**
- The delivery's **Response 200** badge after redelivery (proof the gateway accepted it).
- The `X-GitHub-Event: code_scanning_alert` header in the request payload.

**Narrative (say this):**
> "Now I'll light the fuse. Rather than wait for a fresh push, I'm going to *redeliver* a real webhook payload — this is the exact event GitHub fires when CodeQL re-scans the repo and flags a finding. Watch the response code: a clean 200. That payload just landed on our FastAPI gateway — a stateless service holding zero GitHub tokens and zero secrets. From here on, no human touches the keyboard."

---

## Step 3 — Under the Hood *(The Terminal & Gateway State)*

**Visual:** Split screen — left: the terminal streaming `docker compose logs -f`; right: the Devin dashboard at `app.devin.ai`.

**Action:**
1. Snap to the terminal the instant you redeliver so the audience sees the lines arrive live.
2. Trace the lifecycle out loud as it scrolls: `webhook_received` → `alert_parsed` → `devin_dispatch_start` → `devin_dispatch_success`.
3. Pivot to the Devin dashboard and point at the **brand-new session** that just appeared; click in to show it cloning the repo.

**What to look for on screen:**
- The `[OBSERVABILITY]` lines, ending on `status=dispatched` with a real `session_id` and `session_url`.
- That same session ID now live on the Devin dashboard, working autonomously.

**Narrative (say this):**
> "Here's the part I'm proud of. Look at this log stream — it's not noise, and it's deliberately not a wall of latency metrics. It's pure, deterministic state: received, parsed, dispatched. An engineering leader can glance at this and know *exactly* where every task stands. And there — `status=dispatched`, with a session ID. Flip over to the Devin dashboard… and there it is. That ID just spun up its own cloud VM, it's cloning Superset right now, and it's going to read the vulnerable file, write the fix, and run the tests — all on its own machine, while we keep talking."

---

## Step 4 — The Delivery *(The Unified PR)*

**Visual:** Back to GitHub → the repo's **Pull Requests** tab.

**Action:**
1. Let the session work for a beat (or cut to a pre-warmed result if time is tight).
2. Refresh the Pull Requests tab.
3. Open the resulting PR; show the title, the branch name, and the diff.

**What to look for on screen:**
- The standardized title: **`Fix: Clear-text logging of sensitive information`**.
- The source branch: **`security/alert-<NUMBER>`** — one branch, not a pile of duplicates.
- A real diff plus passing checks, sitting in **review** state (not merged).

**Narrative (say this):**
> "And we've closed the loop. Notice the title — `Fix:` followed by the exact vulnerability name. Every PR this system opens reads like that, so your dashboard becomes self-documenting. Now look at the branch: `security/alert-` and the alert number. That's the whole deduplication strategy. Because the branch name is derived straight from the alert, a redelivery or a re-scan lands its commits *on this same branch* — GitHub folds them into this one PR instead of spraying duplicates off master. One alert, one branch, one clean PR. And critically — it is *not* merged. It's a complete, tested patch waiting for an engineer's sign-off. We didn't take humans out of the loop. We took the busywork out, and left the judgment in."

---

## Recovery & Timing Notes

- **If the session is slow:** keep narrating Step 3 (the architecture story buys you time), or cut to a PR you pre-generated minutes earlier — the audience can't tell, and the result is identical.
- **If a redelivery 500s:** redeliver a second payload; the gateway is idempotent on branch name, so nothing duplicates.
- **Total target:** ~90 seconds. Steps 1–2 ≈ 35s, Step 3 ≈ 35s, Step 4 ≈ 20s.
- **Hand-off back to slides:** after Step 4, advance to *Clean Enterprise Delivery* and resume the scripted narration.
