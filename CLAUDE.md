# Project Rules

This is the single file every agent (and every human) reads at the start of a session. It contains the non-negotiable rules. For the full picture of the system — mission, architecture, harness schema, templates, definition of done — read these in order:

1. [`REQUIREMENTS.md`](REQUIREMENTS.md) — the definition of done (product, feature, non-negotiable capabilities)
2. [`ROADMAP.md`](ROADMAP.md) — the current execution plan (which phase we're in, what's next)
3. [`factory-blueprint.md`](factory-blueprint.md) — the product vision (vibe code up front, mechanic in the back)
4. [`docs/architecture.md`](docs/architecture.md) — the four system views with diagrams
5. [`docs/harness-schema.md`](docs/harness-schema.md) — the per-customer harness contract
6. [`docs/templates/`](docs/templates/) — Slack manifest + vault starter + starter skills (including `grill-me`)
7. [`mechanic/config/AGENTS.md`](mechanic/config/AGENTS.md) — Mechanic Agent workflow (four operations + TDD requirements)
8. [`docs/claude-agent-sdk-deep-dive.md`](docs/claude-agent-sdk-deep-dive.md) — Agent SDK reference

---

## Core Principles

These apply to every change, every commit, every line of code.

1. **Vibes up front, mechanics behind.** Prototyping is fast, freeform, human-in-the-loop. Quality is enforced after the fact, mechanically, by the Mechanic loop. The two are sequential, not opposed.
2. **Mechanical verification over trust.** Every invariant that matters is enforced by a test or a gate. "The prompt says to" is not a control.
3. **Root cause every issue.** No workarounds that create debt. If a test fails, fix the cause — not the test. If a bug is a symptom of a bad design, fix the design.
4. **Fail loud, never silent.** A crash you can see beats a wrong answer you can't. Swallowed exceptions are the enemy.
5. **Hostile input by default.** Any Slack user, any LLM output, any file written inside the Worker container is adversarial until proven otherwise.
6. **Customer trust is the product.** Slow and never-embarrassing beats fast and occasionally-wrong.
7. **Architect for change.** LLMs will be modifying this codebase weekly. Readability and testability beat cleverness.
8. **YAGNI.** Don't build for speculative requirements. Delete code we're not actively supporting. Reintroduce later if needed — git history is the archive.

---

## Test-Driven Development (Mandatory)

**Write the test FIRST, then fix the code.** This applies to all bug fixes and new features.

For bug fixes:
1. Write a test that reproduces the exact failure.
2. Run it — confirm it FAILS (proves the test catches the bug).
3. Fix the code.
4. Run it — confirm it PASSES.
5. Name the test descriptively: `test_<component>_<bug_description>`.

For new features:
1. Write tests that define the expected behavior.
2. Run them — confirm they fail (feature doesn't exist yet).
3. Implement the feature.
4. Run them — confirm they pass.

No code change is complete without its test. This is non-negotiable.

---

## Testing

Run the full pipeline test suite with:

```bash
uv run --python 3.13 \
  --with docker,"slack_sdk>=3.41.0","slack_bolt>=1.27.0",pytest \
  pytest tests/test_pipeline.py tests/test_e2e_integration.py tests/test_docker_integration.py -m "not slow"
```

For the slow real-service integration tests (Docker + real Claude API + real GitHub):

```bash
doppler run --project chat-force --config dev -- \
  uv run --python 3.13 \
    --with docker,"slack_sdk>=3.41.0","slack_bolt>=1.27.0",claude-agent-sdk,pytest \
    pytest tests/test_worker_integration.py tests/test_mechanic_integration.py tests/test_full_pipeline_integration.py -v -s
```

Rules:
- All non-slow tests must pass before committing.
- Slow tests cost money (real API calls) and should be run before any merge to main, on demand locally, and in CI on merge.
- CI runs on every push via `.github/workflows/ci.yml`.

---

## Safety Rules (non-negotiable)

1. **Do not commit or push to `main`.** Use branches and PRs. Main is the known-good line.
2. **Every accepted change must be reviewable.** The pipeline exists to produce auditable diffs. No direct mutations.
3. **Revert, don't patch forward.** If a regression lands on `main`, revert it. Don't try to fix it forward in place.
4. **Keep secrets out of code, logs, and prompts.** Use Doppler-injected env vars (`ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `SLACK_BOT_TOKEN`, per-bot `*_SLACK_*_TOKEN`). Never log a secret. Never embed one in a URL that gets logged.
5. **Worker permissions are container-scoped only.** The Worker uses Agent SDK `permission_mode="bypassPermissions"` inside Docker. Do not reintroduce host-level approval hacks or weaken the container isolation.
6. **No external side effects without explicit approval.** Posting publicly, sending email, pushing to main, calling paid APIs beyond budget — all require the human in the loop.
7. **If containment is unclear, stop.** Preserve state, collect evidence, ask. Do not improvise on shared resources.
8. **Root cause bugs, never mask symptoms.** A test failure means there's a real problem. Fix the problem, not the test.

---

## Runtime Conventions

The engine and Worker have a strict contract on file paths, env vars, and commands. Do not change these without updating every consumer.

### Python + tooling

- Python 3.13 only. Local commands use `uv run --python 3.13 --with <deps>`.
- Pipeline CLI entrypoint: `python -m pipeline.main --task "..."` (or the equivalent `uv run` form).
- Never hand-edit `pyproject.toml` or add dependencies without declaring them in the `uv run --with` command used to run tests/the listener.

### Worker runtime contract

Inside the Worker container, these paths are the canonical IPC surface between the Worker and the engine:

| Path | Direction | Purpose |
|------|-----------|---------|
| `/tmp/session-complete` | Worker → host | Sentinel file. Touched by the Stop hook after a turn completes. The host polls for it. |
| `/tmp/latest-response.txt` | Worker → host | Plain-text response from the most recent turn. |
| `/tmp/tool-log.jsonl` | Worker → host | Append-only JSONL audit trail of every tool call. |
| `/tmp/usage.json` | Worker → host | Token counts and cost for the session. |
| `/tmp/next-message.txt` | host → Worker | Multi-turn follow-up message. Written by the host via `docker cp`, then the host chowns it to the `worker` user. The entrypoint reads and unlinks it. |
| `/tmp/worker-error.txt` | Worker → host | Crash trace. Written by the entrypoint's outer exception handler. |

These are defined in `worker/entrypoint.py` and consumed in `pipeline/worker_manager.py`. If you change one, change both.

### Auth

- `ANTHROPIC_API_KEY` is the canonical env var for Claude access (both Worker-inside-container and host-side Mechanic). Per-bot scoping comes later.
- `GITHUB_TOKEN` is used by `PRCreator` for git clone/push and `gh` CLI. Injected via git credential helper, not embedded in URLs.
- Per-bot Slack tokens follow the pattern `<SLUG>_SLACK_BOT_TOKEN` and `<SLUG>_SLACK_APP_TOKEN` (e.g., `BLACK_TIE_SLACK_BOT_TOKEN`). Declared in the harness's `workspace.yaml`, resolved from Doppler at engine startup.

### Branch naming

- Automated PR branches use the prefix `agent-sdk/auto/<timestamp>-<slug>`.
- Human branches: whatever makes sense, but never `main`.

### Harness contract

Every customer deployment is:

1. The `chat-force` engine (this repo), installed once per host.
2. A `harness-<slug>` repo cloned to `HARNESS_PATH`.
3. A systemd unit that pairs them via `doppler run -- python -m pipeline.slack_listener`.
4. A Slack App created from the harness's `slack-manifest.json`.
5. Secrets in Doppler under a per-customer namespace.

See `docs/harness-schema.md` for the full schema and required files.

---

## Engineering Meta-Rules

- **Act as orchestrator when building.** Delegate implementation work to sub-agents (Codex CLI for code writing, Claude agents for research and review) when the task is substantial. Keep your own context clean.
- **Every substantive change gets reviewed.** For anything beyond a one-line fix, run Codex review + a Claude architect pass before merging.
- **One true set of docs.** Delete docs you're not maintaining. Reintroduce later if needed. Git history is the archive.
- **No hidden state.** If it matters, it's in a file in the repo or a secret in Doppler. Never in someone's head, never in a Slack DM, never in a one-off config on one machine.
