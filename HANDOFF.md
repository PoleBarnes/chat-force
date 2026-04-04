# HANDOFF — Digital Workforce Platform

> **Read this first.** This document is the entry point for any new agent session.
> It describes the current architecture, what is implemented, and the rules that govern changes.

---

## What This Project Is

A self-improving AI agent platform. Leo handles customer-facing work in a sandboxed Worker container. Each run produces a mechanical changeset. A separate Mechanic reviews that changeset and decides whether it is good enough to become a PR. Human review remains the final gate. The system is designed so the codebase can improve over time without direct mutation of `main`.

The platform originally used OpenClaw. That runtime has been replaced by the **Claude Agent SDK** (`pip install claude-agent-sdk`). The Worker now runs the SDK inside Docker, and the Mechanic runs on the host through the SDK's `query()` interface.

---

## Repository Layout

```text
chat-force/
  HANDOFF.md
  JOURNAL.md
  REQUIREMENTS.md
  ORCHESTRATOR-PROMPT.md
  PIVOT-PLAN.md
  SPRINT-PLAN.md
  CLAUDE.md
  Digital-Workforce-Platform-FINAL-v3.1.md
  base-config.yaml

  worker/
    Dockerfile                       # python:3.13-slim + claude-agent-sdk
    entrypoint.py                    # Worker runtime, hooks, sentinel, usage, tool log

  pipeline/
    main.py                          # CLI pipeline entrypoint
    worker_manager.py                # Worker container lifecycle + polling
    mechanic_manager.py              # Host-side Mechanic via Agent SDK query()
    changeset_extractor.py           # git diff, docker diff, telemetry, artifacts
    session_manager.py               # Multi-message session lifecycle
    pr_creator.py                    # PR creation via gh CLI
    slack_handler.py                 # Slack notifications
    config.py

  mechanic/
    config/                          # Mechanic prompt context

  mechanics/                         # Mechanic prompts and evaluation criteria
  skills/                            # Leo skills in markdown
  sops/                              # SOP templates in YAML
  orchestrator/                      # LangGraph code for future structured workflows
  audit/                             # Audit logging + secret patterns
  security/                          # Security docs and guards
  cron/                              # Scheduled behavior configs
  docker/
    config/
      workspace/                     # Leo workspace markdown files
      slack-devbot-manifest.yaml

  docs/
    claude-agent-sdk-deep-dive.md

  scripts/
  tests/
```

**Removed in the Agent SDK pivot:**
- `worker/hooks/`
- `pipeline/response_parser.py`
- `pipeline/webhook_server.py`
- `docker/.devcontainer/`
- `docker/config/openclaw.json`
- `docker/config/auth-profiles.json`
- `security/exec-approvals.json`

---

## Architecture: The Self-Improving Loop

```text
Slack message or CLI task
    |
    v
[Pipeline Orchestrator on Host]
    |
    v
[Worker Container]
    python:3.13-slim
    Claude Agent SDK via ClaudeSDKClient
    worker/entrypoint.py
    plain-text response written to /tmp/latest-response.txt
    completion signaled by /tmp/session-complete
    |
    v
[Changeset Extraction on Host]
    git diff
    docker diff
    container logs
    output artifacts
    |
    v
[Mechanic on Host]
    Claude Agent SDK via query()
    reviews the changeset
    returns approval or rejection
    |
    v
[GitHub PR]
    approved changes only
    |
    v
[Human Review]
    merge or reject
```

The important change is that the Worker is still isolated in Docker, but the Mechanic is no longer another container. The host process runs the Mechanic directly through the Agent SDK. Completion is no longer driven by webhook callbacks; the host polls for the sentinel file at `/tmp/session-complete`.

### Key Principles

1. **Fresh Worker sandbox.** The Worker starts from the current repo state inside a Docker image built from `worker/Dockerfile`.
2. **Mechanical evidence first.** The system trusts diffs, logs, and copied artifacts over agent self-reporting.
3. **Mechanic is separate from the Worker.** Review happens outside the Worker sandbox on the host.
4. **Responses are plain text.** The Worker persists text to `/tmp/latest-response.txt`; the old OpenClaw JSON response format is gone.
5. **Every accepted change becomes a PR.** No direct writes to `main`.
6. **Human review is mandatory.** Travis is still the final decision-maker.

---

## Agent SDK Architecture

The platform now uses a split Agent SDK pattern:

- **Worker:** runs in Docker, uses `ClaudeSDKClient`, and owns the mutable sandbox where Leo edits files and uses tools.
- **Mechanic:** runs on the host, uses `query()`, and reviews the extracted changeset without sharing the Worker's container.

In the Worker, `worker/entrypoint.py` builds the system prompt from the workspace markdown files, starts the SDK client, and installs Python hook callbacks for:

- pre-tool logging
- post-tool logging
- stop/completion handling

Those callbacks replace the old `worker/hooks/` directory and webhook-based lifecycle. The Worker writes:

- `/tmp/latest-response.txt` for the latest plain-text response
- `/tmp/tool-log.jsonl` for the JSONL audit trail
- `/tmp/usage.json` for token and cost tracking
- `/tmp/session-complete` as the completion sentinel

Authentication now uses `CLAUDE_CODE_OAUTH_TOKEN`. Inside the Worker container, permissions are handled with Agent SDK `permission_mode="bypassPermissions"` rather than an external approvals JSON file. The SDK also gives the system a clean path to structured output when a task benefits from schema-constrained results.

---

## Mechanic System

| Mechanic | Role | Trigger | Status |
|----------|------|---------|--------|
| **A (Worker Analysis)** | Reviews Worker changesets and session output | After each Worker run | Implemented on host via Agent SDK |
| **B (Workflow Analysis)** | Reviews structured workflow execution quality | After workflow runs | Deferred |
| **C (The Scout)** | Proposes experiments and tooling research | Daily cron | Prompt exists, runtime not wired |
| **Meta-Mechanic** | Reviews the mechanics themselves | Weekly | Deferred |

**Golden rule:** no change without evidence. The default outcome is rejection unless the changeset is clearly useful, correct, and safe.

---

## What Exists Today

### Built

- Worker image in [worker/Dockerfile](/Users/travis/chat-force/worker/Dockerfile) using `python:3.13-slim` and `claude-agent-sdk`
- Worker runtime in [worker/entrypoint.py](/Users/travis/chat-force/worker/entrypoint.py) with Python callbacks, plain-text response capture, sentinel completion, tool log, and usage tracking
- Host-side pipeline in [pipeline/main.py](/Users/travis/chat-force/pipeline/main.py)
- Worker lifecycle management and sentinel polling in [pipeline/worker_manager.py](/Users/travis/chat-force/pipeline/worker_manager.py)
- Host-side Mechanic evaluation via Agent SDK `query()` in [pipeline/mechanic_manager.py](/Users/travis/chat-force/pipeline/mechanic_manager.py)
- Changeset extraction, PR creation, Slack notifications, and session management in `pipeline/`
- Skills in `skills/`, SOP templates in `sops/`, and Mechanic prompts in `mechanics/`
- Audit logging and secret-pattern support in `audit/`
- Test suite in `tests/`

### Current Reality

- The OpenClaw runtime and its config files are gone.
- The Mechanic does not run in Docker anymore.
- Webhook completion flow is gone; sentinel polling is the runtime contract now.
- LangGraph still exists in `orchestrator/`, but it is for future structured workflows, not the core self-improvement loop.

---

## Technology Stack

| Component | Technology | Notes |
|-----------|------------|-------|
| Primary agent runtime | Claude Agent SDK | Installed with `pip install claude-agent-sdk` |
| Worker environment | Docker + `python:3.13-slim` | One Worker container per session/run |
| Worker interface | `ClaudeSDKClient` | Long-lived SDK client inside the container |
| Mechanic interface | Agent SDK `query()` | Runs directly on the host |
| Auth | `CLAUDE_CODE_OAUTH_TOKEN` | Replaces `ANTHROPIC_AUTH_TOKEN` |
| Secrets | Doppler | Environment injection, never hardcoded |
| Interface | Slack + CLI | Slack for user interaction, CLI for direct pipeline runs |
| Source control | GitHub | Approved changes become PRs |
| Python tooling | Python 3.13 + `uv` | Preferred local execution path |
| Future workflows | LangGraph | Reserved for structured SOP execution |

---

## Safety Rules

1. **Do not commit or push to `main`.** Use branches and PRs.
2. **Every accepted change must be reviewable.** The pipeline exists to produce auditable diffs.
3. **Main is the known-good line.** Revert regressions; do not patch around them on `main`.
4. **Test the current pipeline, not the dead gateway path.** Use the Python pipeline entrypoint and the test suite; do not rely on old `openclaw agent ...` commands.
5. **Keep secrets out of code, logs, and prompts.** Use Doppler-provided env vars such as `CLAUDE_CODE_OAUTH_TOKEN`, `GITHUB_TOKEN`, and `SLACK_BOT_TOKEN`.
6. **Treat Worker permissions as container-scoped.** The Worker uses Agent SDK `bypassPermissions` inside Docker; do not reintroduce host-level approval hacks.
7. **Do not deploy external side effects without explicit approval.**
8. **If containment is unclear, stop.** Preserve the current state, collect evidence, and avoid improvising on shared resources.

---

## Key Reference Files

| File | Purpose |
|------|---------|
| `Digital-Workforce-Platform-FINAL-v3.1.md` | Original product and business spec |
| `REQUIREMENTS.md` | Requirements tracker |
| `JOURNAL.md` | Engineering history and decisions |
| `ORCHESTRATOR-PROMPT.md` | Build orchestrator guidance |
| `mechanics/evaluation-criteria.yaml` | Mechanic scoring rules |
| `worker/entrypoint.py` | Core Worker Agent SDK runtime |
| `pipeline/main.py` | Self-improving loop entrypoint |

---

## Conventions

- **Python:** use Python 3.13. Local commands should prefer `uv run --python 3.13 ...`.
- **Pipeline entrypoint:** run the loop with `python -m pipeline.main --task "..."` or the equivalent `uv run` form.
- **Worker completion:** completion is signaled by `/tmp/session-complete`, not a webhook.
- **Worker responses:** the canonical response artifact is plain text in `/tmp/latest-response.txt`.
- **Audit artifacts:** tool usage is recorded in `/tmp/tool-log.jsonl`; usage and cost are recorded in `/tmp/usage.json`.
- **Skills:** markdown files in `skills/`.
- **SOPs:** YAML files in `sops/`.
- **Workspace files:** markdown files in `docker/config/workspace/`, loaded into the Worker system prompt.
- **Automation branches:** generated PR branches use the `agent-sdk/auto/...` prefix.
