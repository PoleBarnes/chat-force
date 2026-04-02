# SPRINT PLAN — Prototype Self-Improving Loop

> **Sprint Goal:** Build the self-improving OpenClaw loop end-to-end, from CLI trigger to GitHub PR.
>
> **Linear Issues:** TRA-219, TRA-220, TRA-221
>
> **Branch:** `sprint/prototype-loop` (create from `main`)

---

## Success Criteria

The prototype is successful when:

1. You can run a CLI command with a work instruction
2. A Worker container spins up, executes the instruction via OpenClaw, and signals completion
3. The changeset is extracted mechanically (git diff + docker diff JSON + transcript)
4. The Mechanic receives the payload, evaluates it, and returns a structured verdict
5. If approved, a GitHub PR is created with the changes and the Mechanic's evaluation
6. If rejected, the changes are discarded with a logged reason
7. The entire pipeline runs without human intervention from trigger to PR

---

## Architecture Overview

```
CLI: python pipeline/main.py --task "Add a skill that counts words"
    |
    v
[Pipeline Orchestrator]  ---- pure Python, no AI, just plumbing
    |
    |  1. Build/start Worker container (OpenClaw + config repo cloned inside)
    v
[Worker Container]  ---- fresh Docker, config cloned at build time
    |                     Leo executes the task freely inside the sandbox
    |                     afterTurn hook POSTs to orchestrator webhook
    |  2. Worker signals completion (or timeout kills it)
    v
[Changeset Extraction]  ---- mechanical, not self-reported
    |                         Layer 1: git diff (config/skill changes)
    |                         Layer 2: docker diff (system changes)
    |                         Layer 3: execution telemetry (logs, exit code, timing)
    |                         Layer 4: OpenClaw logs + memory
    |  3. Assemble changeset bundle JSON
    v
[Mechanic Container]  ---- separate OpenClaw instance, code-reviewer persona
    |                       Evaluates: Meaningful? Correct? Safe? Minimal? Reproducible?
    |                       Outputs structured verdict to /output/verdict.json
    |  4. Parse verdict
    v
[Verdict Router]
    |
    +--> APPROVE --> extract approved files --> create branch --> open PR --> notify Slack
    |
    +--> REJECT --> log reason --> optionally notify Slack --> destroy containers
```

---

## Directory Layout (New Files)

```
chat-force/
  SPRINT-PLAN.md              # This file

  pipeline/                   # NEW — The self-improving loop orchestrator
    __init__.py
    main.py                   # CLI entry point
    config.py                 # Configuration (env vars, defaults, timeouts)
    worker_manager.py         # Build/start/stop Worker containers
    changeset_extractor.py    # git diff, docker diff, transcript extraction
    mechanic_manager.py       # Start Mechanic, pass payload, get verdict
    pr_creator.py             # GitHub branch/PR creation via gh CLI
    slack_handler.py          # Slack ack/response (stub for prototype)
    webhook_server.py         # HTTP endpoint for afterTurn webhook

  worker/                     # NEW — Worker container definition
    Dockerfile
    entrypoint.sh
    hooks/
      notify-orchestrator/
        HOOK.md
        handler.ts

  mechanic/                   # NEW — Mechanic container definition
    Dockerfile
    config/
      SOUL.md
      IDENTITY.md
      AGENTS.md
```

**Important:** The existing `orchestrator/` directory contains LangGraph code (graphs, nodes) for future structured workflows. Do NOT modify it. The new pipeline lives in `pipeline/` to avoid confusion.

---

## Workstreams

Workstreams 1-4 have no dependencies on each other and can be built in parallel.
Workstream 5 depends on 1 and 4.
Workstream 6 depends on all others.

```
    WS1 (Pipeline)
    WS2 (Worker Container)     --+--> WS5 (PR + Slack) --> WS6 (E2E Test)
    WS3 (Changeset Extraction) --+
    WS4 (Mechanic Config)      --+
```

---

### Workstream 1: Pipeline Orchestrator

**Delegated to: Backend Agent**

Build `pipeline/` as a Python CLI application. This is the spine of the loop.

#### Files to Create

**`pipeline/__init__.py`** — Empty init.

**`pipeline/config.py`** — All configuration in one place.

```python
"""Pipeline configuration — all tunables live here."""

import os
from dataclasses import dataclass, field


@dataclass
class PipelineConfig:
    # Docker
    worker_image: str = "chat-force-worker:latest"
    mechanic_image: str = "chat-force-mechanic:latest"
    docker_network: str = "chat-force-net"

    # Timeouts (seconds)
    worker_timeout: int = 600      # 10 minutes
    mechanic_timeout: int = 300    # 5 minutes

    # Paths
    output_base: str = "/tmp/chat-force-runs"
    config_repo_url: str = "https://github.com/YOUR_ORG/chat-force.git"

    # GitHub
    github_repo: str = "YOUR_ORG/chat-force"
    pr_branch_prefix: str = "openclaw/auto"

    # Webhook
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8787

    # Secrets (from Doppler — never hardcode values here)
    github_token_env: str = "GITHUB_TOKEN"
    anthropic_token_env: str = "ANTHROPIC_AUTH_TOKEN"
    slack_token_env: str = "SLACK_BOT_TOKEN"

    def __post_init__(self):
        """Resolve env vars and create output directory."""
        os.makedirs(self.output_base, exist_ok=True)
```

**`pipeline/main.py`** — CLI entry point. Runs the full loop sequentially.

```python
"""
CLI entry point for the self-improving loop.

Usage:
    python pipeline/main.py --task "Add a skill that counts words in a text file"
"""

import argparse
import json
import logging
import sys
import uuid
from datetime import datetime, timezone

from pipeline.config import PipelineConfig
from pipeline.worker_manager import WorkerManager
from pipeline.changeset_extractor import ChangesetExtractor
from pipeline.mechanic_manager import MechanicManager
from pipeline.pr_creator import PRCreator
from pipeline.slack_handler import SlackHandler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run_pipeline(task: str, config: PipelineConfig) -> dict:
    """Execute the full self-improving loop. Returns a run summary dict."""
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    logger.info(f"[{run_id}] Starting pipeline for task: {task}")

    worker = WorkerManager(config, run_id)
    extractor = ChangesetExtractor(config, run_id)
    mechanic = MechanicManager(config, run_id)
    pr_creator = PRCreator(config, run_id)
    slack = SlackHandler(config, run_id)

    result = {"run_id": run_id, "task": task, "status": "started"}

    try:
        # Step 1: Run Worker
        logger.info(f"[{run_id}] Step 1: Starting Worker container")
        container_id = worker.start(task)
        worker.wait_for_completion()
        result["worker_container"] = container_id

        # Step 2: Extract changeset
        logger.info(f"[{run_id}] Step 2: Extracting changeset")
        changeset = extractor.extract(container_id)
        result["changeset_path"] = changeset["bundle_path"]

        # Step 3: Run Mechanic
        logger.info(f"[{run_id}] Step 3: Starting Mechanic container")
        verdict = mechanic.evaluate(changeset)
        result["verdict"] = verdict["verdict"]

        # Step 4: Act on verdict
        if verdict["verdict"] == "approve":
            logger.info(f"[{run_id}] Step 4: Mechanic APPROVED — creating PR")
            pr_url = pr_creator.create(changeset, verdict)
            result["pr_url"] = pr_url
            result["status"] = "pr_created"
            slack.notify_approval(run_id, task, pr_url, verdict)
        else:
            logger.info(f"[{run_id}] Step 4: Mechanic REJECTED — {verdict.get('rejection_reason', 'no reason')}")
            result["rejection_reason"] = verdict.get("rejection_reason", "unknown")
            result["status"] = "rejected"
            slack.notify_rejection(run_id, task, verdict)

    except TimeoutError as e:
        logger.error(f"[{run_id}] Timeout: {e}")
        result["status"] = "timeout"
        result["error"] = str(e)
    except Exception as e:
        logger.error(f"[{run_id}] Pipeline error: {e}", exc_info=True)
        result["status"] = "error"
        result["error"] = str(e)
    finally:
        # Always clean up containers (but keep them around for debugging if error)
        if result["status"] in ("pr_created", "rejected"):
            worker.cleanup()
            mechanic.cleanup()
        else:
            logger.warning(f"[{run_id}] Keeping containers alive for debugging")

    # Write run summary
    summary_path = f"{config.output_base}/{run_id}/summary.json"
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    with open(summary_path, "w") as f:
        json.dump(result, f, indent=2)

    logger.info(f"[{run_id}] Pipeline finished: {result['status']}")
    return result


def main():
    parser = argparse.ArgumentParser(description="Run the self-improving OpenClaw loop")
    parser.add_argument("--task", required=True, help="The work instruction to execute")
    parser.add_argument("--dry-run", action="store_true", help="Print config and exit")
    args = parser.parse_args()

    config = PipelineConfig()

    if args.dry_run:
        print(json.dumps(config.__dict__, indent=2))
        sys.exit(0)

    result = run_pipeline(args.task, config)

    if result["status"] == "pr_created":
        print(f"\nPR created: {result['pr_url']}")
        sys.exit(0)
    elif result["status"] == "rejected":
        print(f"\nRejected: {result.get('rejection_reason', 'unknown')}")
        sys.exit(0)
    else:
        print(f"\nPipeline failed: {result['status']} — {result.get('error', 'unknown')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

**`pipeline/worker_manager.py`** — Docker container lifecycle for the Worker.

Design notes:
- Uses `docker` Python SDK (not subprocess)
- Builds the Worker image if not present
- Passes the task via environment variable `TASK_INSTRUCTION`
- Starts a webhook server thread to receive the afterTurn signal
- Waits for either: completion signal via webhook, container exit, or timeout
- Does NOT use `--rm` — container must survive for changeset extraction

Key methods:
```python
class WorkerManager:
    def __init__(self, config: PipelineConfig, run_id: str): ...
    def start(self, task: str) -> str:  # returns container_id
    def wait_for_completion(self) -> None:  # blocks until done or timeout
    def cleanup(self) -> None:  # remove container
```

**`pipeline/changeset_extractor.py`** — See Workstream 3 for full specification.

**`pipeline/mechanic_manager.py`** — Docker container lifecycle for the Mechanic.

Design notes:
- Mounts the changeset bundle at `/changeset:ro`
- Mounts an output volume at `/output`
- Passes the task description as `TASK_DESCRIPTION` env var
- Waits for `/output/verdict.json` to appear (poll or inotify)
- Parses and validates the verdict against the schema

Key methods:
```python
class MechanicManager:
    def __init__(self, config: PipelineConfig, run_id: str): ...
    def evaluate(self, changeset: dict) -> dict:  # returns verdict
    def cleanup(self) -> None:  # remove container
```

**`pipeline/pr_creator.py`** — GitHub PR creation.

Design notes:
- Uses `gh` CLI (subprocess) for simplicity — no PyGithub dependency
- Creates branch: `openclaw/auto/<timestamp>-<slugified-description>`
- Copies approved files from Worker container to a temp checkout
- Commits and pushes the branch
- Creates PR with Mechanic's `pr_title` and `pr_body`
- Returns the PR URL

Key methods:
```python
class PRCreator:
    def __init__(self, config: PipelineConfig, run_id: str): ...
    def create(self, changeset: dict, verdict: dict) -> str:  # returns PR URL
```

**`pipeline/slack_handler.py`** — Stub for prototype.

Design notes:
- Uses `slack_sdk` with `SLACK_BOT_TOKEN` from Doppler
- For prototype: just posts to a hardcoded admin channel
- Two methods: `notify_approval(...)` and `notify_rejection(...)`
- All methods are no-ops if `SLACK_BOT_TOKEN` is not set (graceful degradation)

**`pipeline/webhook_server.py`** — HTTP server for afterTurn webhook.

Design notes:
- Lightweight: `http.server` or `aiohttp` — no Flask/FastAPI
- Single endpoint: `POST /hooks/after-turn`
- Sets a threading.Event when called
- The WorkerManager's `wait_for_completion()` waits on this event

#### Dependencies

```
docker>=7.0
slack_sdk>=3.0
```

Run with: `uv run --python 3.13 --with docker,slack_sdk python pipeline/main.py --task "..."`

Or create a `pipeline/requirements.txt`:
```
docker>=7.0
slack_sdk>=3.0
```

---

### Workstream 2: Worker Container

**Delegated to: Infrastructure Agent**

Build the Worker Dockerfile and afterTurn hook. The Worker is a throwaway OpenClaw instance that executes a single task.

#### Files to Create

**`worker/Dockerfile`**

```dockerfile
# Worker container — executes a single task in OpenClaw
# Config repo is CLONED inside (not mounted) so docker diff captures all changes

FROM ghcr.io/openclaw/openclaw:latest

# Install git (needed for changeset extraction via exec)
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Clone the config repo at build time
ARG CONFIG_REPO_URL
ARG CONFIG_BRANCH=main
RUN git clone --depth 1 --branch ${CONFIG_BRANCH} ${CONFIG_REPO_URL} /workspace/config

# Copy workspace files into OpenClaw's expected location
RUN cp /workspace/config/docker/config/workspace/*.md /home/node/.openclaw/workspace/ 2>/dev/null || true

# Copy skills
RUN cp /workspace/config/skills/*.md /home/node/.openclaw/workspace/skills/ 2>/dev/null || true

# Install the afterTurn hook
COPY hooks/notify-orchestrator/ /home/node/.openclaw/hooks/notify-orchestrator/

# Copy entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# The orchestrator sets these at runtime:
#   TASK_INSTRUCTION — what to do
#   ORCHESTRATOR_WEBHOOK_URL — where to POST afterTurn
#   ANTHROPIC_AUTH_TOKEN — LLM access

ENTRYPOINT ["/entrypoint.sh"]
```

**Build note:** The Dockerfile references the OpenClaw base image. Verify the actual image name and registry. It may be a local image built from the existing devcontainer — check with `docker images | grep -i claw`.

**`worker/entrypoint.sh`**

```bash
#!/bin/bash
set -euo pipefail

# Validate required env vars
: "${TASK_INSTRUCTION:?TASK_INSTRUCTION env var is required}"
: "${ANTHROPIC_AUTH_TOKEN:?ANTHROPIC_AUTH_TOKEN env var is required}"

echo "[Worker] Starting OpenClaw with task: ${TASK_INSTRUCTION}"

# Initialize git in the config directory so we can diff later
cd /workspace/config
git add -A
git commit -m "baseline" --allow-empty 2>/dev/null || true

# Run the task via OpenClaw CLI
openclaw agent \
  --agent main \
  --message "${TASK_INSTRUCTION}" \
  --json \
  > /tmp/openclaw-output.json 2>&1 || true

echo "[Worker] OpenClaw execution complete"

# The afterTurn hook fires during execution.
# After the final turn, we signal explicit completion:
if [ -n "${ORCHESTRATOR_WEBHOOK_URL:-}" ]; then
  curl -sf -X POST "${ORCHESTRATOR_WEBHOOK_URL}/hooks/task-complete" \
    -H "Content-Type: application/json" \
    -d "{\"container_id\": \"$(hostname)\", \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"status\": \"complete\"}" \
    || echo "[Worker] Warning: failed to notify orchestrator"
fi

# Keep container alive briefly for changeset extraction
# The orchestrator will stop it explicitly
echo "[Worker] Waiting for orchestrator to extract changeset..."
sleep infinity
```

**`worker/hooks/notify-orchestrator/HOOK.md`**

```markdown
# notify-orchestrator

OpenClaw afterTurn hook that notifies the pipeline orchestrator after each turn.

## Trigger
afterTurn

## Behavior
POSTs minimal metadata to the orchestrator webhook endpoint.
Does not block execution — fire and forget.
```

**`worker/hooks/notify-orchestrator/handler.ts`**

```typescript
/**
 * afterTurn hook — notifies the pipeline orchestrator.
 * Posts minimal metadata: container ID, timestamp, session info.
 * Fire-and-forget: does not block the next turn.
 */

interface AfterTurnPayload {
  sessionId: string;
  turnNumber: number;
  // other fields from OpenClaw's afterTurn interface
}

export default async function handler(payload: AfterTurnPayload): Promise<void> {
  const webhookUrl = process.env.ORCHESTRATOR_WEBHOOK_URL;
  if (!webhookUrl) {
    console.warn("[notify-orchestrator] ORCHESTRATOR_WEBHOOK_URL not set, skipping");
    return;
  }

  const data = {
    container_id: process.env.HOSTNAME || "unknown",
    session_id: payload.sessionId,
    turn_number: payload.turnNumber,
    timestamp: new Date().toISOString(),
    event: "after_turn",
  };

  try {
    await fetch(`${webhookUrl}/hooks/after-turn`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
      signal: AbortSignal.timeout(5000), // 5s timeout — don't block
    });
  } catch (err) {
    // Fire and forget — log but don't throw
    console.warn(`[notify-orchestrator] Failed to notify: ${err}`);
  }
}
```

**Implementation note on hooks:** The exact OpenClaw hook format (file naming, export signature, registration) must be verified against the running OpenClaw version. Check `/home/node/.openclaw/` inside the existing container for examples. The handler above is a best-guess starting point.

#### Key Design Decisions

1. **Config cloned, not mounted.** This is critical. If the config repo were volume-mounted, `docker diff` would not capture changes to those files. Cloning at build time means all file modifications show up in `docker diff` and `git diff`.

2. **No `--rm` flag.** The container must survive after task completion so the orchestrator can run `docker exec` and `docker cp` for changeset extraction.

3. **`sleep infinity` at the end.** Keeps the container alive after task completion. The orchestrator calls `docker stop` when extraction is done.

4. **Git baseline commit.** The entrypoint creates a baseline commit in `/workspace/config` so that `git diff` cleanly shows only the changes made during execution.

---

### Workstream 3: Changeset Extraction

**Delegated to: Backend Agent**

Build the mechanical change capture system in `pipeline/changeset_extractor.py`. This is the most important part of the loop — it establishes ground truth about what the Worker actually did, independent of what the Worker claims it did.

#### Extraction Layers

**Layer 1 — Git diff (config/skill changes):**

```bash
# Get structured diff of all changes to the config repo
docker exec $CONTAINER bash -c "cd /workspace/config && git diff"
docker exec $CONTAINER bash -c "cd /workspace/config && git status --porcelain"
docker exec $CONTAINER bash -c "cd /workspace/config && git ls-files --others --exclude-standard"

# Get individual changed file contents (for PR creation later)
docker exec $CONTAINER bash -c "cd /workspace/config && git diff --name-only"
```

**Fallback:** If the container is stopped (not running), `docker exec` won't work. In that case:
```bash
docker cp $CONTAINER:/workspace/config /tmp/runs/$RUN_ID/config-snapshot/
# Then diff against a fresh clone of the repo
```

**Layer 2 — Docker diff (system changes):**

```bash
# Filesystem changes at the container level
docker diff $CONTAINER
# Returns lines like: A /path/to/new/file, C /path/to/changed/file, D /path/to/deleted/file
```

Parse the output into structured JSON:
```json
{
  "added": ["/path/to/new/file", ...],
  "changed": ["/path/to/changed/file", ...],
  "deleted": ["/path/to/deleted/file", ...]
}
```

Filter out noise (temp files, caches, log rotations). Include a default noise filter:
```python
NOISE_PATTERNS = [
    "/tmp/",
    "/var/log/",
    "/var/cache/",
    "/root/.cache/",
    "/home/node/.npm/",
    "/home/node/.cache/",
    "*.pyc",
    "__pycache__",
    ".git/",
]
```

**Layer 3 — Execution telemetry:**

```bash
# Container logs (stdout + stderr)
docker logs $CONTAINER

# Exit code
docker inspect $CONTAINER --format='{{.State.ExitCode}}'

# Timing
docker inspect $CONTAINER --format='{{.State.StartedAt}}'
docker inspect $CONTAINER --format='{{.State.FinishedAt}}'
```

**Layer 4 — OpenClaw internal logs:**

```bash
# OpenClaw session logs
docker cp $CONTAINER:/home/node/.openclaw/logs/ /tmp/runs/$RUN_ID/openclaw-logs/

# OpenClaw memory state (what the agent remembers)
docker cp $CONTAINER:/home/node/.openclaw/workspace/memory/ /tmp/runs/$RUN_ID/openclaw-memory/

# OpenClaw output (if written to a known path)
docker cp $CONTAINER:/tmp/openclaw-output.json /tmp/runs/$RUN_ID/openclaw-output.json
```

**Note:** The exact OpenClaw log and memory paths must be verified against the running instance. Check with `docker exec $CONTAINER ls -la /home/node/.openclaw/`.

#### Changeset Bundle Schema

The extractor assembles all layers into a single JSON bundle saved to disk:

```json
{
  "run_id": "20260401-143022-a1b2c3d4",
  "task": "Add a skill that counts words in a text file",
  "timestamp": "2026-04-01T14:30:22Z",
  "worker_container": "abc123def456",

  "git_changes": {
    "diff": "full unified diff text",
    "status": "output of git status --porcelain",
    "new_files": ["skills/word-count.md"],
    "modified_files": [],
    "deleted_files": [],
    "file_contents": {
      "skills/word-count.md": "full file content..."
    }
  },

  "docker_changes": {
    "added": ["/home/node/.openclaw/workspace/skills/word-count.md"],
    "changed": ["/home/node/.openclaw/logs/session.log"],
    "deleted": [],
    "filtered_noise": ["/tmp/openclaw-output.json", "/var/cache/..."]
  },

  "telemetry": {
    "exit_code": 0,
    "started_at": "2026-04-01T14:30:22Z",
    "finished_at": "2026-04-01T14:35:10Z",
    "duration_seconds": 288,
    "container_logs": "truncated stdout+stderr (last 500 lines)"
  },

  "openclaw_logs": {
    "session_log_path": "/tmp/chat-force-runs/20260401-143022-a1b2c3d4/openclaw-logs/",
    "memory_path": "/tmp/chat-force-runs/20260401-143022-a1b2c3d4/openclaw-memory/",
    "output_path": "/tmp/chat-force-runs/20260401-143022-a1b2c3d4/openclaw-output.json"
  },

  "bundle_path": "/tmp/chat-force-runs/20260401-143022-a1b2c3d4/"
}
```

#### Implementation

```python
class ChangesetExtractor:
    def __init__(self, config: PipelineConfig, run_id: str): ...

    def extract(self, container_id: str) -> dict:
        """Run all extraction layers and return the changeset bundle."""
        bundle = {}
        bundle["git_changes"] = self._extract_git_changes(container_id)
        bundle["docker_changes"] = self._extract_docker_changes(container_id)
        bundle["telemetry"] = self._extract_telemetry(container_id)
        bundle["openclaw_logs"] = self._extract_openclaw_logs(container_id)
        # Write bundle to disk
        self._save_bundle(bundle)
        return bundle

    def _extract_git_changes(self, container_id: str) -> dict: ...
    def _extract_docker_changes(self, container_id: str) -> dict: ...
    def _extract_telemetry(self, container_id: str) -> dict: ...
    def _extract_openclaw_logs(self, container_id: str) -> dict: ...
    def _save_bundle(self, bundle: dict) -> None: ...
    def _filter_noise(self, paths: list[str]) -> tuple[list[str], list[str]]: ...
```

---

### Workstream 4: Mechanic Configuration

**Delegated to: Backend Agent**

Configure the Mechanic as a separate OpenClaw instance with a code-reviewer persona. The Mechanic receives the changeset bundle and outputs a structured verdict.

#### Files to Create

**`mechanic/Dockerfile`**

```dockerfile
# Mechanic container — evaluates changesets from the Worker
# Read-only access to changeset, writes verdict to /output

FROM ghcr.io/openclaw/openclaw:latest

# Install gh CLI for PR creation support
RUN apt-get update && apt-get install -y gh git && rm -rf /var/lib/apt/lists/*

# Copy Mechanic workspace config
COPY config/SOUL.md /home/node/.openclaw/workspace/SOUL.md
COPY config/IDENTITY.md /home/node/.openclaw/workspace/IDENTITY.md
COPY config/AGENTS.md /home/node/.openclaw/workspace/AGENTS.md

# The orchestrator mounts at runtime:
#   /changeset:ro — the changeset bundle from the Worker
#   /output       — where the Mechanic writes its verdict

# Env vars set at runtime:
#   TASK_DESCRIPTION — what the Worker was asked to do
#   ANTHROPIC_AUTH_TOKEN — LLM access

ENTRYPOINT ["openclaw", "agent", "--agent", "main"]
```

**`mechanic/config/SOUL.md`**

```markdown
# SOUL — The Mechanic

You are The Mechanic. You evaluate code changes produced by AI agents.

## Core Values

1. **Safety first.** If a change could cause harm, data loss, or security issues — reject it.
2. **Correctness matters.** Code must do what it claims to do.
3. **Minimalism is a virtue.** The best change is the smallest change that solves the problem.
4. **When in doubt, reject.** The cost of rejecting a good change is another attempt. The cost of approving a bad change is a regression on main.
5. **Evidence over narrative.** Trust the diff, not the agent's description of what it did.

## What You Are NOT

- You are NOT a collaborator. You do not help fix the code.
- You are NOT lenient. You do not approve changes because they look "close enough."
- You do not consider effort or intent. Only the diff matters.

## Decision Framework

APPROVE when ALL of these are true:
- The change is meaningful (solves the stated task)
- The change is correct (does what it claims)
- The change is safe (no secrets, no destructive ops, no security holes)
- The change is minimal (no unnecessary additions)
- The change is reproducible (another agent could verify it)

REJECT when ANY of these are true:
- The change contains secrets, tokens, or credentials
- The change modifies security controls or safety mechanisms
- The change is incomplete (partial solution, TODO comments, placeholder code)
- The change introduces unnecessary complexity
- The change has obvious bugs or logic errors
- The change modifies files outside the expected scope
- The diff is empty (nothing was actually changed)
```

**`mechanic/config/IDENTITY.md`**

```markdown
# IDENTITY

Name: The Mechanic
Role: Changeset evaluator for the Digital Workforce Platform
Created by: Travis Hendrickson

You review changesets produced by Worker agents. You receive a bundle containing:
- The original task instruction
- Git diffs of all code/config changes
- Docker filesystem diffs
- Execution telemetry (logs, timing, exit codes)
- OpenClaw session logs

You output a structured verdict to /output/verdict.json.
```

**`mechanic/config/AGENTS.md`**

```markdown
# AGENTS

You work alone. You are the sole evaluator of this changeset.

## Your Process

1. **Read the task instruction.** Understand what was asked.
2. **Read the git diff.** This is your primary evidence. What files changed? What was added, modified, deleted?
3. **Check for red flags.** Secrets, security changes, destructive operations, scope creep.
4. **Evaluate correctness.** Does the code do what the task asked for? Are there bugs?
5. **Evaluate minimalism.** Is there unnecessary code? Extra files? Over-engineering?
6. **Check the docker diff.** Did the agent install packages? Modify system files? This is secondary evidence.
7. **Review telemetry.** Did the container exit cleanly? Were there errors in the logs?
8. **Write your verdict.**

## Output Format

You MUST write your verdict as JSON to /output/verdict.json. Use this exact schema:

    {
      "verdict": "approve" or "reject",
      "confidence": 0.0 to 1.0,
      "summary": "one-paragraph summary of your evaluation",
      "evaluation": {
        "meaningful": { "pass": true/false, "notes": "..." },
        "correct":    { "pass": true/false, "notes": "..." },
        "safe":       { "pass": true/false, "notes": "..." },
        "minimal":    { "pass": true/false, "notes": "..." },
        "reproducible": { "pass": true/false, "notes": "..." }
      },
      "pr_title": "short title for the PR (if approved)",
      "pr_body": "PR description with evaluation details (if approved)",
      "files_to_include": ["list of file paths to include in the PR"],
      "files_to_exclude": ["list of file paths to exclude (noise, temp files)"],
      "rejection_reason": "if rejected, explain why"
    }

## Rules

- The `verdict` field MUST be exactly "approve" or "reject". No other values.
- If ANY evaluation criterion has `"pass": false`, the verdict MUST be "reject".
- The `confidence` field reflects how sure you are of your verdict (0.0 = uncertain, 1.0 = certain).
- `files_to_include` should list only the files that belong in the PR. Exclude test artifacts, temp files, caches.
- `files_to_exclude` should list files that changed but should NOT be in the PR (with a brief reason in the notes).
- `pr_title` should be concise (under 70 characters) and describe the change, not the process.
- `pr_body` should include your full evaluation so the human reviewer has context.
```

#### Verdict Schema Reference

```json
{
  "verdict": "approve | reject",
  "confidence": 0.0,
  "summary": "string",
  "evaluation": {
    "meaningful": { "pass": false, "notes": "string" },
    "correct":    { "pass": false, "notes": "string" },
    "safe":       { "pass": false, "notes": "string" },
    "minimal":    { "pass": false, "notes": "string" },
    "reproducible": { "pass": false, "notes": "string" }
  },
  "pr_title": "string",
  "pr_body": "string",
  "files_to_include": [],
  "files_to_exclude": [],
  "rejection_reason": "string"
}
```

---

### Workstream 5: PR Creation and Slack Notification

**Delegated to: Infrastructure Agent**

**Depends on:** Workstream 1 (pipeline structure) and Workstream 4 (verdict schema)

Build the PR creation pipeline in `pipeline/pr_creator.py` and the Slack notification stub in `pipeline/slack_handler.py`.

#### PR Creation Flow (on APPROVE)

```
1. Clone the repo to a temp directory
2. Create branch: openclaw/auto/<YYYYMMDD-HHMMSS>-<slug>
   e.g.: openclaw/auto/20260401-143022-add-word-count-skill
3. For each file in verdict.files_to_include:
   - docker cp $WORKER_CONTAINER:/workspace/config/<file> /tmp/checkout/<file>
4. Stage, commit, push the branch
5. gh pr create \
     --repo $GITHUB_REPO \
     --base main \
     --head $BRANCH \
     --title "$verdict.pr_title" \
     --body "$verdict.pr_body"
6. Return the PR URL
```

#### PR Body Format

The Mechanic's `pr_body` should follow this template (instruct in AGENTS.md):

```markdown
## Mechanic Evaluation

**Task:** <original task instruction>
**Verdict:** APPROVED (confidence: 0.85)

### Evaluation

| Criterion | Pass | Notes |
|-----------|------|-------|
| Meaningful | Yes | Created the requested word-count skill |
| Correct | Yes | Logic handles edge cases |
| Safe | Yes | No secrets, no destructive operations |
| Minimal | Yes | Single file, no unnecessary additions |
| Reproducible | Yes | Standard skill file format |

### Summary
<Mechanic's one-paragraph summary>

### Files Included
- `skills/word-count.md`

### Files Excluded
- `/tmp/openclaw-output.json` (execution artifact)

---
*Automated evaluation by The Mechanic — Digital Workforce Platform*
```

#### Rejection Flow (on REJECT)

```
1. Log the rejection to /tmp/chat-force-runs/$RUN_ID/rejection.json:
   {
     "run_id": "...",
     "task": "...",
     "verdict": { ...full verdict... },
     "timestamp": "..."
   }
2. Post to Slack (if token available):
   "[Rejected] Task: <task> — Reason: <rejection_reason>"
3. Stop and remove Worker + Mechanic containers
```

#### Slack Notification Stub

```python
class SlackHandler:
    def __init__(self, config: PipelineConfig, run_id: str):
        self.channel = "C_ADMIN_CHANNEL"  # hardcoded for prototype
        token = os.environ.get(config.slack_token_env)
        self.client = WebClient(token=token) if token else None

    def notify_approval(self, run_id, task, pr_url, verdict):
        if not self.client:
            logger.info(f"[Slack stub] Approved: {pr_url}")
            return
        self.client.chat_postMessage(
            channel=self.channel,
            text=f"*PR Created* — {verdict.get('pr_title', 'Untitled')}\n"
                 f"Task: {task}\n"
                 f"PR: {pr_url}\n"
                 f"Confidence: {verdict.get('confidence', '?')}",
        )

    def notify_rejection(self, run_id, task, verdict):
        if not self.client:
            logger.info(f"[Slack stub] Rejected: {verdict.get('rejection_reason', '?')}")
            return
        self.client.chat_postMessage(
            channel=self.channel,
            text=f"*Rejected* — {task}\n"
                 f"Reason: {verdict.get('rejection_reason', 'unknown')}",
        )
```

---

### Workstream 6: End-to-End Test

**Delegated to: Testing Agent**

**Depends on:** All other workstreams.

#### Test Scenario

```bash
python pipeline/main.py --task "Add a skill that counts the words in a text file"
```

#### Expected Behavior

1. **Worker starts:** Container `chat-force-worker:latest` runs, Leo receives the task
2. **Leo creates a skill:** A new file appears at `/workspace/config/skills/word-count.md` (or similar)
3. **Worker signals completion:** afterTurn hook fires, then task-complete endpoint
4. **Changeset extracted:**
   - `git diff` shows one new file in `skills/`
   - `docker diff` shows the file creation
   - Telemetry shows clean exit
5. **Mechanic evaluates:**
   - Meaningful: yes (skill created for the stated task)
   - Correct: yes (skill file is valid markdown, logic makes sense)
   - Safe: yes (no secrets, no destructive ops)
   - Minimal: yes (single file, nothing extra)
   - Reproducible: yes (follows existing skill format)
   - Verdict: APPROVE
6. **PR created:**
   - Branch: `openclaw/auto/YYYYMMDD-HHMMSS-add-word-count-skill`
   - PR contains one file: `skills/word-count.md`
   - PR body has the Mechanic's evaluation table
7. **Slack notified:** Message posted with PR link (or logged if no token)

#### Validation Checklist

```
[ ] pipeline/main.py --task "..." exits 0
[ ] Worker container started and stopped cleanly
[ ] Changeset bundle JSON written to /tmp/chat-force-runs/<run_id>/
[ ] Changeset contains at least one new file in skills/
[ ] Mechanic container started and stopped cleanly
[ ] verdict.json written with valid schema
[ ] Verdict is "approve"
[ ] PR branch created on GitHub
[ ] PR contains only the files from files_to_include
[ ] PR body contains the Mechanic evaluation
[ ] Run summary JSON written
[ ] No containers left running after pipeline completes
```

#### Failure Scenarios to Test Later (Not This Sprint)

- Worker times out (10 min) — verify container is killed and failure logged
- Worker produces no changes — verify Mechanic rejects with "empty diff"
- Worker produces unsafe changes — verify Mechanic rejects
- Mechanic times out — verify container is killed and failure logged
- Mechanic produces invalid JSON — verify pipeline handles gracefully
- GitHub token missing — verify PR creation fails with clear error
- Docker not available — verify pipeline fails immediately with clear error

---

## Delegation Pattern

The orchestrating agent should follow this sequence:

```
1. Read this plan (SPRINT-PLAN.md)
2. Read HANDOFF.md for full project context
3. Create branch: sprint/prototype-loop (from main)
4. Spin up sub-agents in parallel:

   [Backend Agent]              [Infrastructure Agent]
   - WS1: pipeline/*.py        - WS2: worker/Dockerfile, entrypoint, hooks
   - WS3: changeset extractor  (WS2 has no code deps on other workstreams)
   - WS4: mechanic config

5. When WS1 + WS4 are done:

   [Infrastructure Agent]
   - WS5: pr_creator.py, slack_handler.py
   (These depend on the pipeline structure from WS1 and verdict schema from WS4)

6. When all workstreams are done:

   [Testing Agent]
   - WS6: End-to-end test
   - Verify the full loop works

7. Review all output
8. Run tests: uv run --python 3.13 --with docker,slack_sdk pytest tests/
9. Commit to sprint/prototype-loop
10. Open PR to main
```

---

## Key Dependencies and Prerequisites

| Dependency | Status | Action if Missing |
|------------|--------|-------------------|
| Docker (OrbStack) | Installed on Mac Mini | Required — cannot proceed without it |
| OpenClaw container image | Running in devcontainer | Verify image name: `docker images \| grep -i claw` |
| `GITHUB_TOKEN` in Doppler | Check: `doppler secrets get GITHUB_TOKEN` | Create if missing: needs `repo` scope |
| `ANTHROPIC_AUTH_TOKEN` in Doppler | Exists | None |
| `SLACK_BOT_TOKEN` in Doppler | May not exist | Pipeline works without it (graceful degradation) |
| `gh` CLI | Should be installed | `brew install gh` if missing |
| `uv` | Should be installed | `curl -LsSf https://astral.sh/uv/install.sh \| sh` if missing |
| `container-diff` | Not installed | `brew install container-diff` (optional — nice-to-have for structured package diff) |

### Pre-Flight Check Script

Before starting the sprint, run this to verify prerequisites:

```bash
#!/bin/bash
echo "=== Pre-Flight Check ==="

echo -n "Docker: "; docker info > /dev/null 2>&1 && echo "OK" || echo "MISSING"
echo -n "gh CLI: "; gh --version > /dev/null 2>&1 && echo "OK" || echo "MISSING"
echo -n "uv: "; uv --version > /dev/null 2>&1 && echo "OK" || echo "MISSING"
echo -n "Python 3.13: "; python3.13 --version > /dev/null 2>&1 && echo "OK" || echo "MISSING"

echo -n "GITHUB_TOKEN: "; doppler secrets get GITHUB_TOKEN --plain > /dev/null 2>&1 && echo "OK" || echo "MISSING"
echo -n "ANTHROPIC_AUTH_TOKEN: "; doppler secrets get ANTHROPIC_AUTH_TOKEN --plain > /dev/null 2>&1 && echo "OK" || echo "MISSING"
echo -n "SLACK_BOT_TOKEN: "; doppler secrets get SLACK_BOT_TOKEN --plain > /dev/null 2>&1 && echo "OK (optional)" || echo "NOT SET (ok for prototype)"

echo -n "OpenClaw image: "; docker images --format '{{.Repository}}:{{.Tag}}' | grep -i claw && echo "OK" || echo "CHECK MANUALLY"

echo "=== Done ==="
```

---

## First Test Scenario

Simple, verifiable task chosen because it exercises the full loop with minimal risk:

> **"Add a skill that can count the words in a text file."**

Why this task:
- Simple enough to manually verify the output
- Worker should create exactly one new file (`skills/word-count.md`)
- Follows existing skill format (see `skills/` for examples)
- Mechanic should approve it (straightforward, safe, minimal)
- PR should contain just the one skill file
- After merge and container rebuild, the skill should be available to Leo

---

## What NOT to Build in This Sprint

These are explicitly out of scope. Do not start work on any of these:

- **ClawVault integration** — memory system is next sprint
- **Slack-to-Orchestrator routing** — prototype uses CLI trigger only
- **Warm container pool** — prototype creates fresh containers each run
- **Concurrent runs** — prototype is single-threaded
- **CI pipeline for auto-rebuild** — rebuild manually after merge
- **LangGraph workflow integration** — the existing `orchestrator/` code stays untouched
- **Multi-tenant anything** — single user, single agent
- **Container image registry** — build locally for prototype
- **Monitoring/alerting** — check logs manually
- **Rate limiting or quotas** — prototype is dev-only

---

## Reference Files

| File | Why You Need It |
|------|----------------|
| `HANDOFF.md` | Full project context, architecture, conventions, safety rules |
| `JOURNAL.md` | Engineering decision history |
| `Digital-Workforce-Platform-FINAL-v3.1.md` | Original product spec |
| `mechanics/evaluation-criteria.yaml` | Existing Mechanic scoring criteria (reference for SOUL.md) |
| `mechanics/mechanic-a-prompt.md` | Existing Mechanic A prompt (reference for Mechanic config) |
| `skills/*.md` | Examples of well-formed skills (reference for test scenario) |
| `docker/config/workspace/*.md` | Leo's workspace files (mounted into Worker) |
| `docker/config/openclaw.json` | OpenClaw instance config (reference for Dockerfile) |
| `base-config.yaml` | Platform config (models, limits, skills list) |
