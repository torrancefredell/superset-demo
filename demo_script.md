# Autonomous Security Remediation — Demo Script

**Presenter:** Torrance Fredell
**Audience:** VP of Engineering, Senior Technical Architects
**Duration:** 5 minutes
**Format:** Screen share with live dashboard + slides

---

## Phase 1: The Zero-Sum Tradeoff

**[0:00 – 1:00]**

*Open on the title slide. Pause for one beat, then begin.*

> "Thank you for your time. I want to talk about a problem that every engineering organization faces but nobody has solved cleanly — the zero-sum tradeoff between security and velocity.
>
> Here's the reality: tools like CodeQL are excellent at *finding* vulnerabilities. They scan every push, they flag insecure patterns, they generate detailed advisories. But they don't fix anything.
>
> What happens next is the expensive part. A senior engineer gets pulled off their feature sprint to triage an alert. They spend forty-five minutes reading the advisory, understanding the context, and ten minutes writing what is usually a straightforward fix. Multiply that across dozens of alerts per quarter, and you have a pattern: green-field feature development stalls because the team is drowning in brown-field security debt.
>
> The backlog grows. Sprint velocity drops. And the engineers who *should* be building your next competitive advantage are instead writing boilerplate patches for known vulnerability patterns.
>
> What if that entire remediation cycle — from alert to pull request — happened autonomously, without pulling a single engineer off their roadmap?"

*Advance to the "What Is Devin?" slide.*

---

## Phase 2: Meeting the Autonomous Remote Coworker

**[1:00 – 2:00]**

> "This is where Devin comes in — and I want to be precise about what Devin is, because the distinction matters.
>
> Devin is not a local autocomplete plugin. It's not an IDE copilot that burns through your token budget and loses context every time you switch files. Those tools — Claude in your editor, Windsurf, Cursor — they're useful for inline suggestions, but they operate inside *your* session, consuming *your* context window, and they can't take autonomous action.
>
> Devin is a cloud-native, asynchronous remote coworker. It spins up its own isolated virtual machine with its own terminal, its own browser, and its own file system. You give it a task via an API call, and it works in the background — cloning repositories, reading code, writing fixes, running tests, and opening pull requests. It's an engineer that never context-switches, never loses state, and works around the clock.
>
> Now, the system I built to orchestrate this is a lightweight FastAPI gateway. And here's a deliberate architectural decision I want to call out: this gateway is *stateless* and *unauthenticated*. It holds no GitHub API tokens. It stores no repository secrets. It doesn't maintain a database. The only outbound credential is the Devin API token — which is the equivalent of assigning work to a team member. This is by design. For an enterprise deployment, the less your middleware touches sensitive credentials, the smaller your attack surface."

*Advance to the "Security vs. Velocity" slide, then to the architecture slide.*

---

## Phase 3: Git-Native Architecture in Action

**[2:00 – 3:30]**

> "Let me walk you through exactly what happens when a vulnerability is detected.
>
> CodeQL runs on every push to our Apache Superset fork. When it finds a security issue — say, the use of an unsafe YAML loader — GitHub fires a `code_scanning_alert` webhook to our FastAPI gateway.
>
> The gateway receives that payload and does three things. First, it validates the event — we only process `created` and `reopened_by_user` actions. Everything else is ignored. Second, it extracts the metadata we need: the vulnerability description, the file path, the alert URL, and the tool name — all pulled from the nested CodeQL schema under `payload.alert`.
>
> Third — and this is the engineering win I'm most proud of — it computes a *deterministic branch name*: `security/alert-` followed by the unique alert number. So alert number 42 always maps to `security/alert-42`. Always. Every time."

*If live, show the terminal with the curl command. Otherwise, reference the architecture diagram.*

> "Now, why does this matter? The naive approach would be to call the GitHub API on every webhook, search through open pull requests looking for duplicates, and manage state in a database. That requires a GitHub token in your middleware, it introduces race conditions on concurrent webhooks, and it adds latency to every request.
>
> Our approach is different. Because the branch name is deterministic, we don't need to check anything. We pass this branch name directly to Devin with a simple instruction: 'If `security/alert-42` already exists on the remote, check it out and push your fix on top. If it doesn't exist, create it from master.'
>
> GitHub does the rest natively. When you push commits to a branch that already has an open pull request, those commits appear in the existing PR automatically. No duplicate PRs. No API lookups. No tokens in the middleware. The deduplication is handled entirely by Git's own mechanics."

*Pause. Let the architecture sink in.*

> "So when a webhook is redelivered — which happens — or an alert is reopened after a failed fix, the system self-heals. Same branch, same PR, updated fix. Zero clutter."

---

## Phase 4: Clean Enterprise Delivery

**[3:30 – 4:30]**

*Switch to the GitHub PR dashboard or show the demo placeholder slide.*

> "Let me show you what the output looks like on the other side.
>
> Every pull request that Devin opens follows a strict naming convention: 'Fix:' followed by the literal vulnerability name, capitalized. So you see titles like 'Fix: Client-side cross-site scripting' or 'Fix: Clear-text logging of sensitive information.'
>
> This isn't cosmetic. When an engineering leader opens their PR dashboard, they should be able to scan the list and immediately understand what each PR addresses — without clicking into it. Standardized titles make that possible. They also make it trivial to filter, search, and report on security remediation throughput across the organization.
>
> The PR itself contains a complete remediation: the code fix, passing tests, and a description that links back to the original CodeQL alert. Every fix is traceable. Every fix is auditable. And every fix was produced without interrupting a human engineer's workflow."

*If showing live PRs, scroll through them briefly. Point to the titles.*

> "This is what security looks like when it's treated as an automated utility rather than a manual interrupt."

---

## Phase 5: The ROI Mic Drop

**[4:30 – 4:40]**

*Advance to the impact slide or speak directly to camera.*

> "Let me close with the numbers that matter.
>
> Before this system: every CodeQL alert cost approximately one hour of senior engineer time — context-switching, reading the advisory, writing the patch, opening the PR, waiting for review. At dozens of alerts per quarter, that's entire sprint cycles consumed by maintenance work that follows a known, repeatable pattern.
>
> After this system: the time from alert to pull request is measured in minutes, not days. The engineering cost per alert is effectively zero — no context switch, no cognitive load, no sprint disruption. Your senior engineers stay in flow on the features that drive business value.
>
> We've turned security remediation from a reactive interrupt into a proactive utility. It runs in the background, twenty-four seven, and it scales linearly with the number of alerts without scaling your headcount.
>
> The gateway is stateless. The architecture is token-free. The output is clean, standardized, and auditable. And the entire system fits in a single Docker container.
>
> And that brings me to what comes next."

*Advance to the "The Path to Implementation: A Collaborative Pilot" slide.*

---

## Phase 6: From POC to Production & Q&A

**[4:40 – 5:00]**

> "What we've built today is a successful proof of concept. To take this into full production rollout, we want to look at the next steps as a collaborative pilot.
>
> First, we want to sit down with your team to select 3 to 4 direct use cases and specific pain points unique to your organization. From there, we'll run a targeted Proof of Concept with Devin to tackle those exact issues.
>
> After several weeks, we can evaluate the actual ROI generated, and use those concrete results to confidently roll Devin out to more developers and broader use cases.
>
> And finally, this is not a handoff. Our team will work hand-in-hand with your engineers to align this pilot seamlessly with your existing workflows.
>
> I'm happy to take questions — on the architecture, the pilot, or how we'd roll this into your organization."

*Advance to the Q&A slide. Smile. Wait.*

---

## Technical Reference

For the presenter's reference during Q&A:

| Topic | Detail |
|---|---|
| **Gateway** | FastAPI, async, stateless, no GitHub tokens |
| **Dedup strategy** | Deterministic branch: `security/alert-<N>` |
| **PR title format** | `Fix: <Vulnerability Name>` (capitalized) |
| **Accepted actions** | `created`, `reopened_by_user` |
| **Payload schema** | `alert.tool.name`, `alert.rule.description`, `alert.most_recent_instance.location.path` |
| **Devin API** | `POST /v3/organizations/{org_id}/sessions` |
| **Docker** | `docker compose up --build` — single container, no volumes |
| **Repo** | `github.com/torrancefredell/superset-demo` |
| **Target repo** | `github.com/torrancefredell/superset` (Apache Superset fork) |
