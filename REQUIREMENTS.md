# Requirements Tracker — Digital Workforce Platform

> Architecture: Self-improving sandboxed agent with mechanical change capture
> Source spec: `Digital-Workforce-Platform-FINAL-v3.1.md` (v3.1, product vision)
> Linear: TRA-219, TRA-220, TRA-221 (evolved implementation architecture)
> Last updated: 2026-04-01

---

## Status Key

- 🟢 COMPLETE — Built, tested, verified in integration
- 🟡 IN PROGRESS — Partially built or designed, not wired end-to-end
- 🔴 NOT STARTED — No implementation exists
- ⏸️ DEFERRED — Intentionally postponed; not blocking prototype

### Honesty Rules

These rules govern status claims. The 9-reviewer code review found ~18 of 38 green items were over-claimed.

- "Code exists in isolation" is 🟡, not 🟢
- "Config file exists" is 🟡 unless enforcement is implemented
- "Prompt written" is 🟡 unless the mechanic is running and producing output
- "Test passes in unit tests" is 🟡 unless the feature works in the real system
- 🟢 means: a human could use this feature right now and it would work

---

## Definition of Done (Prototype)

The system is DONE when all of the following happen in sequence without human intervention (except the final review):

1. Send Leo a Slack message
2. Leo runs in a fresh sandbox container built from tip of main
3. Leo does the work and responds in Slack
4. Changeset is mechanically extracted (git diff + docker diff)
5. Mechanic evaluates and opens a PR if improvements found
6. Travis reviews and merges (or rejects with no regression)
7. Next Slack message uses the improved Leo
8. ClawVault persists Leo's knowledge across sessions
9. Git revert restores the last working Leo if a merge causes regression

### Prototype Acceptance Criteria

| # | Criterion | Status |
|---|-----------|--------|
| PA-1 | CLI trigger → Worker container spins up → OpenClaw executes → container stops | 🔴 |
| PA-2 | Changeset bundle extracted (git diff + docker diff + transcript + logs) | 🔴 |
| PA-3 | Mechanic evaluates bundle → structured verdict (approve/reject with evidence) | 🔴 |
| PA-4 | Approved → GitHub PR with filtered changes + evaluation | 🔴 |
| PA-5 | Merge → base image rebuilds → next run uses improvement | 🔴 |
| PA-6 | Rejected → changes discarded, logged | 🔴 |
| PA-7 | Full pipeline runs without human intervention from trigger to PR | 🔴 |

---

## 1. Sandbox & Container Lifecycle

Worker containers are disposable. Each session gets a fresh container built from tip of main. Leo starts bare and learns on the job.

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| SBX-1 | Worker Dockerfile builds from config repo at tip of main | 🔴 | No Worker Dockerfile exists. `docker/` has devcontainer config and provisioning scripts for OpenClaw, not for the sandboxed worker image. |
| SBX-2 | Orchestrator script (Python, CLI-triggered) creates/destroys worker containers | 🔴 | No orchestrator script exists. The `orchestrator/` directory contains LangGraph graph definitions (main.py, mechanic_b.py, sop_runner.py), not the Docker orchestration layer. |
| SBX-3 | Container starts from clean image — no pre-loaded state between sessions | 🔴 | No container lifecycle management exists. |
| SBX-4 | Config repo mounted read-only into container (Dockerfile-as-Code) | 🔴 | Concept established (workspace files exist in `docker/config/workspace/`), but no mount logic implemented. |
| SBX-5 | Container gets workspace files (IDENTITY, SOUL, USER, AGENTS, TOOLS) injected at start | 🟡 | Workspace files exist and are deployed to the running OpenClaw devcontainer manually. No automated injection into worker containers. |
| SBX-6 | Container is destroyed after session completes — no persistent state leaks | 🔴 | No container lifecycle management exists. |
| SBX-7 | One agent (Leo), built well — specialization at skill level, not agent level | 🟡 | Leo identity configured (`docker/config/workspace/IDENTITY.md`). Agent dispatch interface exists (`orchestrator/nodes/agents.py`) but routes to multiple agent types — contradicts one-agent model. |
| SBX-8 | Leo starts bare, learns on the job — no pre-loaded skills | 🔴 | Current design has 7 skills pre-loaded in `base-config.yaml` and 8 skill files in `skills/`. Architecture needs to shift to organic learning. |

---

## 2. Mechanical Change Capture

Two-layer mechanical extraction: git diff (what the agent changed in the repo) + docker diff (what the agent changed in the filesystem). No agent self-reporting.

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| MCC-1 | Git diff extraction from worker container after session | 🔴 | No implementation. |
| MCC-2 | Docker diff extraction (filesystem changes) from worker container | 🔴 | No implementation. |
| MCC-3 | Transcript capture (full agent conversation log) | 🔴 | No implementation. OpenClaw logs exist but no extraction pipeline. |
| MCC-4 | Changeset bundle assembly (git diff + docker diff + transcript + logs) | 🔴 | No implementation. |
| MCC-5 | Changeset stored in structured format for Mechanic consumption | 🔴 | No schema defined. |
| MCC-6 | Mechanical extraction only — agent does not self-report changes | 🔴 | Principle established in architecture docs, no enforcement. |

---

## 3. Mechanic System

The Mechanic is a separate OpenClaw instance that evaluates changesets and produces GitHub PRs. It does not run inside the worker container.

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| MCH-1 | Mechanic A prompt written (chat/skill optimization evaluator) | 🟡 | Prompt exists at `mechanics/mechanic-a-prompt.md` (1.4KB). Not running as an OpenClaw instance. |
| MCH-2 | Mechanic B prompt written (workflow optimization evaluator) | 🟡 | Prompt exists at `mechanics/mechanic-b-prompt.md` (1.7KB). LangGraph sub-graph exists (`orchestrator/graphs/mechanic_b.py`) but uses placeholder trace data and is not wired to real sessions. |
| MCH-3 | Mechanic C/Scout prompt written (daily research loop) | 🟡 | Prompt exists at `mechanics/mechanic-c-scout-prompt.md` (2.5KB). Not running. |
| MCH-4 | Meta-Mechanic prompt written (weekly review of mechanics) | 🟡 | Prompt exists at `mechanics/meta-mechanic-prompt.md` (1KB). Not running. |
| MCH-5 | Evaluation criteria defined (scoring weights) | 🟡 | `mechanics/evaluation-criteria.yaml` exists. Not consumed by any running evaluator. |
| MCH-6 | Mechanic runs as separate OpenClaw instance with evaluator persona | 🔴 | No running Mechanic instance. Prompts are files, not deployed personas. |
| MCH-7 | Mechanic receives changeset bundle and produces structured verdict | 🔴 | No verdict schema. Mechanic B graph has scoring logic but operates on placeholder data. |
| MCH-8 | Verdict schema: approve/reject with evidence, confidence, and filtered diff | 🔴 | No schema defined. |
| MCH-9 | Approved verdict → filtered diff → GitHub PR creation | 🔴 | PR creation skill exists (`skills/pr-creation.md`) as reference material, not as automation pipeline. |
| MCH-10 | PR includes evaluation summary, evidence, and filtered changes | 🔴 | No implementation. |
| MCH-11 | Rejected verdict → changes discarded, evaluation logged | 🔴 | No implementation. |
| MCH-12 | Golden rule: default is no change; only improvements that meet threshold proceed | 🟡 | Threshold logic exists in `orchestrator/graphs/mechanic_b.py` (score < 0.7 triggers proposals, confidence >= 0.6). Not running against real data. |

---

## 4. Improvement Ratchet

Git-based improvement loop: merge → rebuild → improved. Reject → discard → no regression.

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| RAT-1 | Approved PR merged → base image automatically rebuilds | 🔴 | No CI pipeline exists. |
| RAT-2 | Next worker container uses rebuilt image with merged improvements | 🔴 | No container rebuild pipeline. |
| RAT-3 | Rejected PR → changes discarded, no modification to main | 🔴 | Git workflow not implemented (though GitHub's PR model naturally handles this). |
| RAT-4 | Git revert of bad merge restores previous working Leo | 🔴 | Git naturally supports this, but no automated regression detection or revert workflow. |
| RAT-5 | CI pipeline: merge to main → rebuild base image → tag → available for next session | 🔴 | No CI/CD pipeline. |
| RAT-6 | All configuration changes tracked in git history | 🟢 | All config is in git (`base-config.yaml`, `skills/`, `sops/`, `mechanics/`, `security/`, `docker/config/`). Verified by repo structure. |
| RAT-7 | No manual config changes — everything flows through PR process | 🔴 | Principle established. No enforcement mechanism. |

---

## 5. ClawVault Memory

Persistent agent memory in a separate git repo with its own PR flow. Survives container destruction.

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| CLV-1 | ClawVault as separate git repo for persistent agent memory | 🔴 | No ClawVault repo exists. |
| CLV-2 | Session lifecycle: vault checked out at container start, changes committed at end | 🔴 | No implementation. |
| CLV-3 | Vault changes go through own PR flow (separate from code changes) | 🔴 | No implementation. |
| CLV-4 | Vault structure supports search and retrieval by topic/date/session | 🔴 | No implementation. |
| CLV-5 | Vault persists across container destruction | 🔴 | No implementation. |
| CLV-6 | Leo's learned knowledge survives session boundaries | 🔴 | No implementation. |

---

## 6. Agent Identity & Skills

Leo is one agent. Specialization happens at the skill level, not by spawning new agents. Leo starts bare and learns organically.

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| AGT-1 | Leo identity configured (name, personality, role) | 🟢 | `docker/config/workspace/IDENTITY.md` deployed. Leo responds correctly via gateway CLI. Verified. |
| AGT-2 | Leo SOUL file (behavioral principles, communication style) | 🟢 | `docker/config/workspace/SOUL.md` exists (2.2KB) and is deployed to OpenClaw. |
| AGT-3 | Leo USER file (Travis's preferences, working style) | 🟢 | `docker/config/workspace/USER.md` exists (1.6KB) and is deployed to OpenClaw. |
| AGT-4 | Leo AGENTS file (available agent types and dispatch rules) | 🟡 | `docker/config/workspace/AGENTS.md` exists (3.6KB). Deployed, but multi-agent dispatch contradicts one-agent architecture. Needs revision for single-agent model. |
| AGT-5 | Leo TOOLS file (available tools and constraints) | 🟢 | `docker/config/workspace/TOOLS.md` exists (591B) and is deployed to OpenClaw. |
| AGT-6 | Skills exist as reference material (markdown with YAML frontmatter) | 🟢 | 7 skill files in `skills/`: ad-campaign-research, ad-campaign-generate, code-review, morning-briefing, pr-creation, research, sop-detection. OpenClaw injects relevant skills into context based on trigger matching. |
| AGT-7 | Skills are the unit of specialization, not separate agents | 🟡 | Skills exist as designed. However, `orchestrator/nodes/agents.py` has a multi-agent dispatch interface with @register_agent decorator, which conflicts with single-agent philosophy. |
| AGT-8 | Leo learns organically — new skills emerge from work, not pre-loaded | 🔴 | Current design pre-loads all 7 skills in `base-config.yaml`. No mechanism for organic skill emergence from completed work. |
| AGT-9 | Skill promotion path: pattern observed → skill proposed → PR → merge → Leo has it | 🔴 | SOP detection skill is written as reference material. No automated pipeline from observation to PR. |

---

## 7. Orchestrator

Pure plumbing layer. Receives triggers, manages Docker containers, coordinates the pipeline. Not an AI — a script.

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| ORC-1 | Orchestrator script (Python, CLI-triggered) | 🔴 | Does not exist. The `orchestrator/` directory contains LangGraph workflows, not the Docker orchestration script. |
| ORC-2 | Receives trigger (CLI, webhook, Slack event) | 🔴 | No trigger handling. |
| ORC-3 | Creates worker container from latest base image | 🔴 | No Docker container management. |
| ORC-4 | Passes task to worker container | 🔴 | No implementation. |
| ORC-5 | Waits for container to complete | 🔴 | No implementation. |
| ORC-6 | Extracts changeset (delegates to MCC layer) | 🔴 | No implementation. |
| ORC-7 | Sends changeset to Mechanic for evaluation | 🔴 | No implementation. |
| ORC-8 | Handles Mechanic verdict (PR creation or discard) | 🔴 | No implementation. |
| ORC-9 | Slack → Orchestrator routing (webhook receives Slack event, triggers pipeline) | 🔴 | No implementation. Slack is connected to OpenClaw via socket mode, but there is no routing from Slack to the orchestrator pipeline. |
| ORC-10 | Orchestrator is stateless — all state lives in git and container lifecycle | 🔴 | No implementation. |

---

## 8. Interface Layer

Customer-facing experience via Slack. Leo is the only visible entity.

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| INT-1 | Slack app "Leo" created and connected via socket mode | 🟢 | App created, socket mode configured, Doppler has SLACK_BOT_TOKEN and SLACK_APP_TOKEN. Leo responds in Slack DMs. |
| INT-2 | Leo responds to messages in Slack | 🟢 | Verified via both Slack DMs and gateway CLI. |
| INT-3 | Leo app icon set | 🟢 | Custom icon generated (Imagen 4.0) and deployed. `docker/leo-icon-final.png`. |
| INT-4 | Progressive disclosure — plan preview before execution | 🔴 | Concept in spec. No Block Kit implementation. Interrupt logic exists in LangGraph graphs but is not connected to Slack. |
| INT-5 | Approval flow with Approve/Reject/Edit buttons (Block Kit) | 🔴 | No Slack Block Kit implementation. LangGraph interrupt/resume pattern exists in code but is not wired to Slack. |
| INT-6 | Morning briefing on presence or /checkin | 🔴 | Cron config written (`cron/morning-briefing.yaml`), skill written (`skills/morning-briefing.md`). Neither deployed nor running. |
| INT-7 | Heartbeat per project channel | 🔴 | Cron config written (`cron/heartbeat.yaml`). Not deployed, not running. |
| INT-8 | Users only see one bot — internal orchestration is invisible | 🟡 | Architecture supports this (Leo is the single Slack app). But Perplexity Computer was added as a visible agent in Slack workspace — contradicts single-bot principle. |
| INT-9 | Thread continuity — full conversation history maintained | 🟡 | Context assembly in `orchestrator/nodes/context.py` supports thread messages with token budget truncation. But no Slack thread fetch API integration exists. |
| INT-10 | Human memory control — deleting messages removes from context | 🔴 | No implementation. |

---

## 9. Security

Exec-approvals, audit logging, secret management, self-modification prevention.

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| SEC-1 | OpenClaw runs in devcontainer (OrbStack) with managed networking | 🟢 | Running. Verified. Docker provisioning scripts at `docker/provision.sh` and `docker/setup.sh`. |
| SEC-2 | Exec-approvals.json defines command allowlist | 🟡 | File exists at `security/exec-approvals.json` (10.9KB) with detailed allowlists and shell metacharacter blocking. No runtime enforcement code — the file is just config with no consumer. |
| SEC-3 | Audit logger implemented | 🟡 | `audit/audit_logger.py` (9.4KB) with JSONL format, secret scrubbing, and structured event logging. Wired to LLM calls in `orchestrator/nodes/llm.py`. Has never produced real audit logs (logs/ directory is empty except .gitkeep). |
| SEC-4 | Secret patterns detection | 🟡 | `audit/secret_patterns.py` (4.8KB) with regex patterns compiled at module load. Used by audit logger's `_scrub_secrets()`. Not tested against real traffic. |
| SEC-5 | Secrets never appear in agent context | 🟡 | `orchestrator/nodes/llm.py` reads from os.environ, never passes secrets to prompts. Correct by design, but never tested with real API calls in the LangGraph orchestrator. |
| SEC-6 | Doppler vault configured | 🟢 | Project: chat-force, config: dev. Contains SLACK_BOT_TOKEN, SLACK_APP_TOKEN, ANTHROPIC_AUTH_TOKEN, OPENCLAW_GATEWAY_TOKEN. Verified working. |
| SEC-7 | Secret injection flow documented | 🟡 | `security/secret-injection.md` (4.2KB) documents the flow. The OpenClaw devcontainer uses Doppler injection at boot. The LangGraph orchestrator's injection flow is documented but not running. |
| SEC-8 | Git pre-push hook for secret scanning | 🟡 | `scripts/git-pre-push-hook.sh` exists. Not verified that it's installed in `.git/hooks/` or that it catches real secrets. |
| SEC-9 | Self-modification prevention documented | 🟡 | `security/self-modification-guard.md` (3.2KB) documents the approach. No runtime enforcement code. |
| SEC-10 | Self-modification prevention enforced at runtime | 🔴 | No runtime enforcement. Worker containers don't exist yet, so the primary prevention mechanism (read-only mounts + disposable containers) isn't in place. |
| SEC-11 | Per-workspace secret scoping | 🔴 | Doppler supports this architecturally. Only one workspace (dev) configured. No multi-workspace secret isolation. |
| SEC-12 | Network allowlists for outbound container traffic | 🔴 | Mentioned in threat mitigations. Not implemented. |

---

## 10. Observability

Circuit breakers, cost tracking, health monitoring.

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| OBS-1 | Per-task token budget (default 100k) | 🟡 | Configured in `base-config.yaml` (`limits.per_task_tokens: 100000`). No runtime enforcement — the orchestrator code doesn't check token counts against this limit. |
| OBS-2 | Per-task time limit (default 30 min) | 🟡 | Configured in `base-config.yaml` (`limits.per_task_timeout_minutes: 30`). No runtime enforcement. |
| OBS-3 | Circuit breakers (token rate, error rate, daily cost, deploy rate) | 🟡 | Configured in `base-config.yaml` (`circuit_breakers` section). No runtime enforcement. |
| OBS-4 | Daily cost limit ($50) | 🟡 | Configured in `base-config.yaml` (`limits.daily_cost_limit_usd: 50.0`). No runtime enforcement. |
| OBS-5 | Health monitoring / /status command | 🔴 | No implementation. |
| OBS-6 | LangSmith traces for every LLM call | 🔴 | Not connected. LangSmith is mentioned in spec but not configured. |
| OBS-7 | Structured logging for pipeline execution | 🔴 | Audit logger exists but the orchestration pipeline that would produce events doesn't exist yet. |

---

## 11. Workflows (Deferred)

LangGraph for structured multi-step tasks with approval gates. Deferred until the core sandbox + mechanic loop is working.

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| WFL-1 | LangGraph main graph (routing → execution → mechanic) | ⏸️ | `orchestrator/graphs/main.py` (26KB) exists. Compilable. Uses Anthropic SDK directly. Not running in production. Deferred: will be reconsidered after core pipeline works. |
| WFL-2 | LangGraph Mechanic B sub-graph (quality scoring) | ⏸️ | `orchestrator/graphs/mechanic_b.py` (16.7KB) exists. Uses placeholder trace data. Deferred. |
| WFL-3 | LangGraph SOP runner (DAG from YAML) | ⏸️ | `orchestrator/graphs/sop_runner.py` (15.8KB) exists. Generates DAG from SOP YAML with depends_on wiring. Deferred. |
| WFL-4 | 3 SOPs encoded as YAML with input schemas | ⏸️ | ad-campaign (17KB, 17 steps, 2 approval gates), landing-page (6KB), email-sequence (7.1KB). Plus SOP template. Deferred. |
| WFL-5 | Interrupt/resume for human approval gates | ⏸️ | LangGraph interrupt_before on preview, deliverable, and mechanic approval nodes. Not wired to Slack. Deferred. |
| WFL-6 | Context assembly (platform → workspace → thread) | ⏸️ | `orchestrator/nodes/context.py` (15.8KB) with 3-tier assembly and token budget truncation. No Slack thread fetch. Deferred. |
| WFL-7 | Task routing (keyword + SOP matching + complexity heuristics) | ⏸️ | `orchestrator/nodes/routing.py` (2.9KB) and `orchestrator/nodes/sop_loader.py` (9.4KB). Standalone modules, not connected to OpenClaw or orchestrator. Deferred. |
| WFL-8 | Checkpointing after every node (Postgres) | 🔴 | LangGraph supports this natively but Postgres is not configured. |
| WFL-9 | Web intake forms from SOP input schemas | 🔴 | SOP YAML has input_schema fields. No web form generation. |

---

## 12. Multi-Tenant (Deferred)

Per-customer containers, workspace isolation.

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| MTN-1 | Per-customer worker containers | ⏸️ | Single OpenClaw instance running. Multi-tenant is deferred until single-tenant prototype works. |
| MTN-2 | Per-workspace secret isolation | ⏸️ | Doppler architecture supports it. Single workspace configured. |
| MTN-3 | Two-layer update model (platform shared vs. customer frozen) | ⏸️ | Designed in spec. Not implemented. |
| MTN-4 | Cross-workspace skill sharing | ⏸️ | Skills are platform-level. No multi-workspace deployment to test sharing. |
| MTN-5 | Google Chat support | ⏸️ | Not started. Slack only for now. |
| MTN-6 | Service tier system (Tier 1: web form, Tier 2: direct Slack) | ⏸️ | Designed in spec. Not implemented. |

---

## 13. Scout / Research (Deferred)

Mechanic C daily research loop — scans for new tools, agents, techniques.

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| SCT-1 | Mechanic C prompt defines research scope and evaluation criteria | 🟡 | Prompt exists at `mechanics/mechanic-c-scout-prompt.md`. Not running. |
| SCT-2 | Daily/weekly research loop execution | ⏸️ | Cron schedule described. No running instance. |
| SCT-3 | Research findings → experiment proposals → Travis review | ⏸️ | Described in prompt. No pipeline. |
| SCT-4 | Meta-Mechanic reviews all mechanics weekly | ⏸️ | Prompt exists at `mechanics/meta-mechanic-prompt.md`. No running instance. |

---

## Test Infrastructure

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| TST-1 | Unit test suite exists | 🟢 | 5 test files: test_orchestrator.py, test_security.py, test_skills.py, test_sops.py, test_cron.py. 96 tests passing as of last run. |
| TST-2 | Test fixtures for real scenarios | 🟢 | `tests/fixtures/`: blacktie-april-campaign.md, ad-campaign-workflow.md, blacktie-context.md. |
| TST-3 | Gateway CLI verified as test harness | 🟢 | `docker exec $CONTAINER_ID openclaw agent --agent main --message "..." --json` works. Verified. |
| TST-4 | Integration tests (end-to-end pipeline) | 🔴 | No integration tests. Unit tests mock all external calls. |
| TST-5 | Tests run in CI | 🔴 | No CI pipeline. Tests run manually via `tests/run_tests.sh`. |

---

## Infrastructure (Built)

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| INF-1 | OpenClaw self-hosted in devcontainer on Mac Mini (OrbStack) | 🟢 | Running. OpenClaw 2026.4.1, gateway live, Claude Opus 4.6. |
| INF-2 | Doppler secrets management | 🟢 | Project: chat-force, config: dev. 4 secrets configured and injected at boot. |
| INF-3 | GitHub repo (PoleBarnes/chat-force) | 🟢 | Repo exists. Main branch stable. Feature branches used for work. |
| INF-4 | Devcontainer configuration | 🟢 | `docker/.devcontainer/` with config files. `docker/provision.sh` (14.6KB), `docker/setup.sh` (3.1KB). |
| INF-5 | OpenClaw config (auth profiles, server settings) | 🟢 | `docker/config/openclaw.json`, `docker/config/auth-profiles.json`. |
| INF-6 | Git-tracked platform configuration | 🟢 | `base-config.yaml` with models, routing, limits, circuit breakers, skills registry. |
| INF-7 | Linear connected for issue tracking | 🟢 | Connected to KiloClaw. TRA-series issues referenced. |
| INF-8 | uv installed for Python toolchain | 🟢 | Installed via brew. Used for clean Python execution. |

---

## Summary Dashboard

| Category | Total | 🟢 | 🟡 | 🔴 | ⏸️ |
|----------|-------|-----|-----|-----|------|
| 1. Sandbox & Container Lifecycle | 8 | 0 | 2 | 6 | 0 |
| 2. Mechanical Change Capture | 6 | 0 | 0 | 6 | 0 |
| 3. Mechanic System | 12 | 0 | 6 | 6 | 0 |
| 4. Improvement Ratchet | 7 | 1 | 0 | 6 | 0 |
| 5. ClawVault Memory | 6 | 0 | 0 | 6 | 0 |
| 6. Agent Identity & Skills | 9 | 5 | 2 | 2 | 0 |
| 7. Orchestrator | 10 | 0 | 0 | 10 | 0 |
| 8. Interface Layer | 10 | 3 | 2 | 5 | 0 |
| 9. Security | 12 | 2 | 7 | 3 | 0 |
| 10. Observability | 7 | 0 | 4 | 3 | 0 |
| 11. Workflows (Deferred) | 9 | 0 | 0 | 2 | 7 |
| 12. Multi-Tenant (Deferred) | 6 | 0 | 0 | 0 | 6 |
| 13. Scout / Research (Deferred) | 4 | 0 | 1 | 0 | 3 |
| Test Infrastructure | 5 | 3 | 0 | 2 | 0 |
| Infrastructure (Built) | 8 | 8 | 0 | 0 | 0 |
| **TOTAL** | **119** | **22** | **24** | **57** | **16** |

### What This Means

- **22 items complete (18%)** — All infrastructure and identity. The foundation is solid.
- **24 items in progress (20%)** — Mostly "code exists but isn't running" or "config exists but isn't enforced." These are building blocks, not features.
- **57 items not started (48%)** — The entire core pipeline (orchestrator, sandbox, change capture, mechanic loop, vault) is unbuilt. This is the prototype.
- **16 items deferred (13%)** — LangGraph workflows, multi-tenant, and Scout. Intentionally postponed.

### Critical Path to Prototype

The minimum viable improvement loop requires these categories to reach 🟢:

1. **Orchestrator** (ORC-1 through ORC-8) — The plumbing that connects everything
2. **Sandbox** (SBX-1 through SBX-6) — Worker containers that Leo runs in
3. **Change Capture** (MCC-1 through MCC-4) — Mechanical extraction of what changed
4. **Mechanic** (MCH-6 through MCH-11) — Evaluation and PR creation
5. **Ratchet** (RAT-1, RAT-2, RAT-5) — CI rebuild on merge

Everything else is either already built (infrastructure, identity), in progress (security, observability), or deferred (workflows, multi-tenant, scout).
