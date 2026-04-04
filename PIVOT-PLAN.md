# PIVOT PLAN: OpenClaw to Claude Agent SDK

> **Branch:** `pivot/agent-sdk` (created from `sprint/prototype-loop`)
> **Date:** 2026-04-04
> **Decision:** Replace OpenClaw with Claude Agent SDK (`pip install claude-agent-sdk`)

---

## Why

OpenClaw brings too many unknowns: Gateway startup (~10s), config files (openclaw.json, auth-profiles.json), black-box response format, exec-approvals system, and we've been working around it rather than using it as designed. The Agent SDK gives us the same Claude Code runtime as a Python library with direct control.

## Architecture

```
Host (the mechanic / orchestrator)
    |
    |-- Slack message arrives
    |-- Session manager routes to container
    |-- Docker SDK: create container from worker image
    |-- docker exec / docker cp: send messages, get responses
    |-- On session idle: inspect container (git diff, docker diff)
    |-- query() on host: Mechanic evaluates changeset
    |-- PR creation or discard
    |-- Docker SDK: destroy container
    |
    v
Docker Container (the worker / Leo)
    |-- pip install claude-agent-sdk (bundled CLI)
    |-- Python entrypoint calls query()
    |-- All tools (Bash, Read, Write, Edit) execute inside container
    |-- Sandboxed by Docker isolation
```

Key principles:
- The orchestrator IS the mechanic (one process)
- Worker runs INSIDE Docker with Agent SDK
- Mechanic runs on HOST, inspects container from outside
- Auth via CLAUDE_CODE_OAUTH_TOKEN (Max subscription)

## Migration Steps

### Step 1: Add dependencies + config changes
- Add `claude-agent-sdk` to `pipeline/requirements.txt`
- Update `pipeline/config.py`: rename token env var, remove webhook fields, add Agent SDK fields
- **Tests:** PipelineConfig instantiates with new defaults

### Step 2: New Worker Dockerfile + Python entrypoint with hooks
- New `worker/Dockerfile` based on `python:3.13-slim` + `pip install claude-agent-sdk`
- New `worker/entrypoint.py` that calls `query()` with system prompt assembled from workspace files
- **Agent SDK configuration in query() call:**
  - `permission_mode="bypassPermissions"` — container is already sandboxed by Docker
  - `allowed_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebSearch", "WebFetch", "Agent", "ComputerUse"]` — full tool access including subagents and computer use
  - `max_budget_usd` — from config, prevents runaway costs
  - `max_turns` — from config, prevents infinite loops
- **Hooks registered in entrypoint:**
  - `PostToolUse` — write every tool call + result to `/tmp/tool-log.jsonl` (ordered audit trail for Mechanic)
  - `PreToolUse` — log tool call intent to `/tmp/tool-log.jsonl`
  - `Stop` — write `/tmp/session-complete` sentinel file, write final usage/cost to `/tmp/usage.json`
  - `SubagentStart/Stop` — log subagent activity to tool log
- **Cost tracking:** Capture usage data (input/output tokens, cost) from each AssistantMessage, write cumulative totals to `/tmp/usage.json`
- **Memory:** Configure Agent SDK memory storage at `/workspace/memory/` so the Mechanic can inspect what Leo learned during the session. Memory changes become part of the changeset.
- Multi-turn via `/tmp/next-message.txt` polling, response to `/tmp/latest-response.txt`
- **Tests:** Docker image builds, entrypoint starts with mocked SDK, hooks write to tool log, usage tracking works

### Step 3: Update WorkerManager
- Remove all webhook imports and code
- `wait_for_completion()` polls for `/tmp/session-complete` sentinel (written by Stop hook)
- `get_response()` reads plain text instead of OpenClaw JSON
- `get_tool_log()` — NEW: reads `/tmp/tool-log.jsonl` from container (ordered audit trail)
- `get_usage()` — NEW: reads `/tmp/usage.json` from container (token counts, cost)
- `get_memory()` — NEW: reads `/workspace/memory/` from container (what Leo learned)
- `send_message()` keeps docker cp mechanism (with chmod fix)
- **Tests:** Update WorkerManager unit tests, mock Docker API, test tool log/usage/memory extraction

### Step 4: Rewrite MechanicManager
- Remove all Docker container code
- `evaluate()` calls `query()` on the host with Mechanic system prompt
- Use structured output for verdict JSON (no more regex parsing)
- Evaluation payload now includes:
  - Git diff + docker diff (existing)
  - Tool log from hooks (ordered sequence of everything the agent did)
  - Usage/cost data (total tokens, cost for the session)
  - Memory changes (what Leo learned — Mechanic decides if memory updates should persist)
- Keep `_prepare_evaluation()` — update to assemble all new data sources
- Keep `_validate_verdict()`
- Move Mechanic persona files to `config/mechanic/`
- **Tests:** Mock `query()`, test verdict parsing, test all data sources in evaluation payload

### Step 5: Delete response_parser.py + webhook_server.py
- Remove files and all imports
- Remove corresponding tests (~35 tests)
- **Tests:** No import errors, remaining tests pass

### Step 6: Update SessionManager
- Remove webhook server creation/management
- Update `_run_mechanic_phase()` for new MechanicManager
- **Tests:** Session lifecycle tests still pass

### Step 7: Update main.py pipeline
- Remove webhook references
- Update feedback loop for new APIs
- **Tests:** CLI pipeline test with mocks

### Step 8: Delete OpenClaw-specific files
- `mechanic/Dockerfile`, `mechanic/entrypoint.sh`
- `worker/entrypoint.sh`, `worker/hooks/`
- `docker/.devcontainer/`, `docker/provision.sh`, `docker/setup.sh`
- `docker/config/openclaw.json`, `docker/config/auth-profiles.json`
- `security/exec-approvals.json`
- `docker/config/workspace/TOOLS.md`
- **Tests:** Full suite passes

### Step 9: Update documentation
- Rewrite HANDOFF.md, REQUIREMENTS.md, JOURNAL.md
- **Tests:** None (documentation)

### Step 10: Integration test with real token
- Run full pipeline with real CLAUDE_CODE_OAUTH_TOKEN
- Simple task -> Worker -> Mechanic -> PR
- **Tests:** End-to-end smoke test

### Step 11: Update Doppler secrets
- Add CLAUDE_CODE_OAUTH_TOKEN
- Generate via `claude setup-token`
- **Tests:** Verify via `doppler run`

## Files to DELETE

| File | Reason |
|------|--------|
| worker/entrypoint.sh | Replaced by entrypoint.py |
| worker/hooks/ | OpenClaw-specific hooks |
| mechanic/Dockerfile | Mechanic runs on host now |
| mechanic/entrypoint.sh | Replaced by host-side query() |
| pipeline/response_parser.py | OpenClaw JSON parsing, not needed |
| pipeline/webhook_server.py | Webhook completion signals, not needed |
| docker/.devcontainer/ | OpenClaw devcontainer |
| docker/provision.sh | OpenClaw provisioning |
| docker/setup.sh | OpenClaw setup |
| docker/config/openclaw.json | OpenClaw config |
| docker/config/auth-profiles.json | OpenClaw auth |
| docker/config/workspace/TOOLS.md | OpenClaw tools list |
| security/exec-approvals.json | OpenClaw exec approvals |

## Files to CREATE

| File | Purpose |
|------|---------|
| worker/Dockerfile | New: python:3.13-slim + claude-agent-sdk |
| worker/entrypoint.py | New: Python entrypoint calling query() |
| config/mechanic/SOUL.md | Moved from mechanic/config/ |
| config/mechanic/IDENTITY.md | Moved from mechanic/config/ |
| config/mechanic/AGENTS.md | Moved from mechanic/config/ |

## Files to MODIFY

| File | Changes |
|------|---------|
| pipeline/config.py | New fields, rename token env var |
| pipeline/worker_manager.py | Remove webhooks, new completion signaling |
| pipeline/mechanic_manager.py | Complete rewrite to host-side query() |
| pipeline/session_manager.py | Remove webhook, update mechanic phase |
| pipeline/main.py | Remove webhook refs, update feedback loop |
| pipeline/changeset_extractor.py | Update agent log paths |
| pipeline/pr_creator.py | Update branch prefix |
| pipeline/slack_listener.py | Remove OpenClaw references in strings |
| pipeline/requirements.txt | Add claude-agent-sdk |
| tests/test_pipeline.py | Remove ~35 tests, add ~35+ new tests |
| HANDOFF.md | Architecture rewrite |
| REQUIREMENTS.md | Update all OpenClaw references |

## New Capabilities Unlocked

- **Subagent spawning** — Leo can delegate to specialized sub-agents
- **Worktree isolation** — Parallel work in git worktrees
- **Computer use** — Screenshots, mouse, keyboard for GUI interaction
- **Built-in memory** — Session-to-session knowledge persistence
- **MCP servers** — Extensible tool ecosystem
- **Structured output** — Enforced JSON schemas for verdicts
- **Per-task cost tracking** — Real token/cost data per query()
- **Permission controls** — Fine-grained tool access per task
- **Python hooks (PreToolUse, PostToolUse, Stop, etc.)** — Real-time observability of every tool call. Hooks run in our Python process, not shell commands. The Mechanic gets a complete ordered log of what the agent did, not just the end-state diff. Key hooks:
  - `PostToolUse` — capture every tool call result for audit/Mechanic analysis
  - `PreToolUse` — audit logging, policy enforcement (block dangerous commands)
  - `Stop` — trigger changeset extraction when agent finishes
  - `SubagentStart/Stop` — track sub-agent activity
  - `PermissionRequest` — auto-approve/deny based on policy

## Delegation Pattern

**You MUST act as an orchestrator.** Do NOT write code yourself. Delegate ALL implementation work to a team of specialized sub-agents. Your role is to:

1. Read this plan (PIVOT-PLAN.md), HANDOFF.md, and CLAUDE.md
2. Branch: `pivot/agent-sdk` (already created)
3. For each step: spawn specialized sub-agents with detailed prompts
4. Parallelize independent steps (e.g., Steps 1+2 can run simultaneously)
5. After each step: verify output, run tests, commit, push
6. Use Codex CLI (`codex exec`) for code reviews alongside Claude agents
7. Follow TDD per CLAUDE.md: instruct agents to write tests FIRST, then implement
8. Keep your own context clean — let agents do the file reading and editing

**Agent team roles:**
- **Codex CLI (`codex exec`)** — ALL code writing. Codex is extremely thorough and careful. Use it for Python, Dockerfiles, entrypoints, tests, config changes.
- **Codex CLI (`codex review`)** — Code reviews after implementation
- **Claude agents (research/planning)** — Research, architecture analysis, codebase exploration, planning
- **Claude agents (orchestration)** — Coordinate work, verify outputs, run tests, commit/push

## Risks

1. Agent SDK behavior in Docker — mitigate with thorough container testing
2. OAuth token auth — test early, have API key fallback
3. Async/sync bridge — use anyio.run() in isolated callsites
4. Multi-turn state — sentinel file polling replaces webhooks
5. No rollback path — execute on feature branch, merge only after verification
