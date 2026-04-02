# HANDOFF — Digital Workforce Platform

> **Read this first.** This document is the single entry point for any new agent session.
> It describes the architecture, what exists, what to build next, and the rules you must follow.

---

## What This Project Is

A self-improving AI agent platform. One agent — Leo — handles customer work (marketing, research, project management) via Slack. Leo runs in a sandboxed Docker container. Every session produces a changeset. A separate Mechanic agent evaluates the changeset. If approved, a PR is created. Human reviews and merges. The next session runs on the improved codebase. The system ratchets forward — it can only get better or stay the same, never regress.

---

## Repository Layout

```
chat-force/                         # Root — this repo IS the agent's codebase
  HANDOFF.md                        # You are here
  JOURNAL.md                        # Engineering decisions and history
  REQUIREMENTS.md                   # Requirements tracker with status
  ORCHESTRATOR-PROMPT.md            # Operating instructions for the build orchestrator
  Digital-Workforce-Platform-FINAL-v3.1.md  # Original product spec (vision, tiers, pricing)
  base-config.yaml                  # Platform-level config

  skills/                           # OpenClaw skills (7 skills, markdown format)
    ad-campaign-research.md
    ad-campaign-generate.md
    code-review.md
    morning-briefing.md
    pr-creation.md
    research.md
    sop-detection.md

  sops/                             # SOP templates (YAML, platform-level)
    ad-campaign.yaml                # 17 steps, 2 approval gates
    landing-page.yaml
    email-sequence.yaml
    sop-template.yaml               # Template for creating new SOPs

  mechanics/                        # Mechanic prompts and evaluation criteria
    mechanic-a-prompt.md            # Worker Analysis (post-session)
    mechanic-b-prompt.md            # Workflow Analysis (deferred)
    mechanic-c-scout-prompt.md      # The Scout (daily research)
    meta-mechanic-prompt.md         # Reviews the mechanics (weekly, deferred)
    evaluation-criteria.yaml

  orchestrator/                     # LangGraph code (for future structured workflows)
    graphs/
    nodes/
    langgraph.json
    requirements.txt

  audit/                            # Audit logging
    audit_logger.py
    secret_patterns.py

  security/                         # Security config
    exec-approvals.json
    secret-injection.md
    self-modification-guard.md

  cron/                             # Proactive behavior configs
    heartbeat.yaml
    morning-briefing.yaml
    standing-orders.yaml

  docker/                           # Container config
    config/
      workspace/                    # Leo's OpenClaw workspace files
        SOUL.md                     # Core personality and values
        IDENTITY.md                 # Who Leo is
        USER.md                     # Travis's preferences
        AGENTS.md                   # Agent team context
        TOOLS.md                    # Available tools
        CRON.md                     # Scheduled behaviors
      openclaw.json                 # OpenClaw instance config
      auth-profiles.json            # Auth configuration
      slack-devbot-manifest.yaml    # Slack app manifest
    leo-icon-final.png
    provision.sh
    setup.sh

  scripts/                          # Utility scripts (pre-push hooks, etc.)
  tests/                            # Test suite (5 test files)
    fixtures/                       # Test fixtures (BlackTie campaign, etc.)
```

**Key structural decisions:**
- `platform/` was eliminated (Python stdlib collision). Its children are now top-level.
- `workspaces/` was removed. Customer config is a deployment concern — OpenClaw workspace files per container, not tracked in this repo.
- SOPs are platform-level templates. The same SOP works for any customer; workspace context customizes output at deploy time.

---

## Architecture: The Self-Improving Loop

This is the core of the system. Understand this and you understand everything.

```
Slack message (or CLI)
    |
    v
[Orchestrator]  ---- pure Python, no AI, just plumbing
    |
    v
[Worker Container]  ---- fresh Docker from tip of main
    |                     Leo runs freely: installs tools, creates skills, modifies config
    |                     Config mounted READ-ONLY (cannot mutate live config)
    v
[Changeset Extraction]  ---- mechanical, not self-reported
    |                         git diff (code/config changes)
    |                         docker diff (environment changes)
    |                         session transcript + container logs
    v
[Mechanic Container]  ---- separate OpenClaw instance, code-reviewer persona
    |                       Evaluates: Meaningful? Correct? Safe? Minimal? Reproducible?
    |                       Agent transcript is additional signal, never primary truth
    v
[GitHub PR]  ---- every change, no matter how small, gets a PR
    |              Mechanic evaluation = PR body
    v
[Human Review]  ---- Travis reviews via Slack notification or GitHub
    |
    +--> Approve + Merge --> new base image --> next session improved
    |
    +--> Reject --> discard --> no regression
```

**The ratchet rule:** Main = known good. The system can only move forward. Rejected changes are thrown away. If a merge causes regression, git revert.

### Key Principles

1. **Leo starts bare.** Just SOUL.md, IDENTITY.md, USER.md, AGENTS.md. No pre-loaded skills. Leo learns on the job.
2. **Sandbox per session.** Each message triggers a fresh container built from tip of main.
3. **Two-layer mechanical capture.** `git diff` for code/config, `docker diff` for environment. The system observes from the outside — no agent self-reporting as primary truth.
4. **Mechanic evaluates.** Separate persona (safety, correctness, minimalism). Receives the full changeset bundle.
5. **Every change is a PR.** No exceptions. No direct mutations.
6. **Human reviews.** Travis is the final gate.

### The Orchestrator

- Pure Python script running on the host
- Coordinates Docker containers: spin up worker, wait, extract changeset, spin up mechanic, wait, create PR
- NO AI reasoning — just docker commands, file copying, status reporting
- Triggered by Slack messages (or CLI for the prototype)

### Dockerfile-as-Code

The entire agent environment is a git artifact:
- Dockerfile + config + skills + requirements — all in this repo
- A skill that needs ffmpeg produces a PR with both the skill file AND the Dockerfile/requirements change
- CI rebuilds the base image on merge to main

---

## Mechanic System

| Mechanic | Role | Trigger | Status |
|----------|------|---------|--------|
| **A (Worker Analysis)** | Evaluates conversation quality + changeset after each Leo session | After each worker turn | Prompt written, needs runtime integration |
| **B (Workflow Analysis)** | Evaluates structured workflow step-by-step performance | After workflow executions | **Deferred** — no workflows exist yet |
| **C (The Scout)** | Scans Twitter/HN/Product Hunt for new tools, proposes experiments | Daily cron | Prompt written |
| **Meta-Mechanic** | Reviews the mechanics themselves | Weekly | **Deferred** |

**Golden rule:** No change without evidence. Default is always: no change.

---

## ClawVault Memory System

Replaces the simple MEMORY.md approach. Designed but not yet built.

- **Git-backed markdown files** with frontmatter, wikilinks, hybrid search (BM25 + semantic embeddings)
- **Vault structure:** `tools/`, `repos/`, `experiments/`, `concepts/`, `decisions/`, `lessons/`, `daily-research/`
- **Session lifecycle:** `clawvault wake` loads prior knowledge, `clawvault sleep` commits to branch
- **Memory changes go through the PR flow** — agent cannot corrupt its knowledge base without review
- The Mechanic can propose vault organization changes, but primarily the agent decides its own structure

---

## One Agent, Built Well

- **Leo** is the single customer-facing agent. Handles research, building, project management.
- Specialization happens at the **skill level**, not the agent level.
- Perplexity Computer is a **tool Leo dispatches to**, not a separate agent.
- The Mechanic is **invisible infrastructure**, not a team member.

---

## LangGraph: Deferred

- NOT used for the improvement loop (the Orchestrator handles that — it is a linear pipeline, not a state machine)
- Reserved for structured multi-step workflows with approval gates (ad campaigns, etc.) — built later when proven SOPs need hard state management
- The existing `orchestrator/` code (graphs, nodes) is the foundation for this future use

---

## What Exists Today

### Built and Working
- 7 OpenClaw skills in `skills/` (reference material for what good skills look like)
- 3 SOPs in `sops/` (ad-campaign, landing-page, email-sequence) + template
- LangGraph orchestrator with Claude integration in `orchestrator/` (for future workflow use)
- Mechanic prompts and evaluation criteria in `mechanics/`
- Audit logging + secret scanning in `audit/`
- Security: exec-approvals, self-modification guard, secret injection docs in `security/`
- Cron configs: heartbeat, morning briefing, standing orders in `cron/`
- Leo's workspace files deployed in `docker/config/workspace/`
- OpenClaw self-hosted in devcontainer on Mac Mini (OrbStack)
- Doppler secrets management configured (project: chat-force, config: dev)
- Slack app "Leo" connected via socket mode
- Gateway CLI verified: `docker exec $CONTAINER_ID openclaw agent --agent main --message "..." --json`
- 9-reviewer code review completed (7 Claude + Codex-mini + GPT-5.4)
- Test suite in `tests/` (5 test files)

### Partially Complete (from review/fix sprint)
- Critical bug fixes (approval gates, DAG wiring) — in progress
- Context truncation, audit integration, security enforcement — in progress
- Skills loading, agent dispatch, dead code cleanup — in progress
- REQUIREMENTS.md accuracy update — todo
- Full test suite re-validation — todo

---

## What to Build Next: Prototype Sprint

**Goal:** Build the self-improving loop end-to-end, CLI-triggered. This is from Linear issues TRA-219, TRA-220, TRA-221.

### Sprint Deliverables (in order)

1. **Orchestrator script** — Python, CLI-triggered. Takes a message, runs the full loop.
   - `python orchestrator.py --message "Research competitor pricing"`
   - No AI in the orchestrator. Pure plumbing: docker commands, file ops, status reporting.

2. **Worker Dockerfile** — Built from this config repo.
   - Install OpenClaw + dependencies
   - Mount config READ-ONLY
   - Leo starts bare (just workspace files), runs freely inside the sandbox

3. **afterTurn webhook** — Completion signaling from the worker container.
   - How the orchestrator knows Leo is done

4. **Changeset extraction** — Run after worker finishes.
   - `git diff` inside the container for code/config changes
   - `docker diff` on the container for environment changes
   - Extract session transcript + container logs
   - Bundle everything into a changeset directory

5. **Mechanic OpenClaw configuration** — Separate instance, code-reviewer persona.
   - Receives the full changeset bundle
   - Outputs a structured verdict: approve/reject + evaluation + filtered changes

6. **GitHub PR creation** — From approved mechanic verdicts.
   - PR body = mechanic evaluation
   - PR diff = filtered changes from the mechanic's approval
   - Slack notification to Travis with PR link

7. **End-to-end test** — CLI message in, PR out.
   - `./orchestrator.py --message "Create a skill for summarizing articles"` should produce a GitHub PR

### Key Linear Issues
- **TRA-219**: Sandbox architecture (worker container, changeset extraction)
- **TRA-220**: ClawVault + research system (memory, Scout mechanic)
- **TRA-221**: Dockerfile-as-Code (environment as git artifact, CI rebuild)

---

## Technology Stack

| Component | Technology | Notes |
|-----------|-----------|-------|
| Primary LLM | Claude Opus 4.6 | Via Anthropic auth token in Doppler |
| Agent Runtime | OpenClaw (KiloClaw, self-hosted) | Devcontainer on Mac Mini, OrbStack |
| Secrets | Doppler | Project: chat-force, Config: dev |
| Interface | Slack (socket mode) | Leo bot app |
| Container | Docker (OrbStack) | One container per session |
| Source Control | GitHub (private) | chat-force repo |
| Python | 3.13, managed with uv | `uv run --python 3.13 --with <deps>` |
| Future Workflows | LangGraph | Local, same container — no cloud needed yet |

---

## Safety Rules

These are non-negotiable. Violating any of these is a session-ending mistake.

1. **DO NOT commit or push to main.** Use feature branches. Always.
2. **Every change is a PR.** No direct mutations to main.
3. **Main = known good.** If something breaks on main, git revert. Never fix forward on main.
4. **Test via gateway CLI** — `openclaw agent --agent main --message "..."`, not Slack.
5. **All secrets in Doppler.** Never hardcode. Never log. Never pass to prompts.
6. **All config in git.** Source-controlled, auditable.
7. **DO NOT deploy anything externally** without explicit approval.
8. **If something goes wrong, stop and contain.** Don't try to fix forward on shared resources.

---

## Key Reference Files

| File | Purpose |
|------|---------|
| `Digital-Workforce-Platform-FINAL-v3.1.md` | Original product spec — vision, service tiers, pricing |
| `REQUIREMENTS.md` | Requirements tracker with completion status |
| `JOURNAL.md` | Engineering decisions, sprint history, current status |
| `ORCHESTRATOR-PROMPT.md` | Build orchestrator operating instructions |
| `mechanics/evaluation-criteria.yaml` | What the Mechanic scores and how |
| `sops/sop-template.yaml` | How to create new SOPs |

---

## Conventions

- **Python:** Use `uv run --python 3.13 --with <deps>` for execution
- **Branches:** Feature branches off main (e.g., `sprint/phase0-buildout`, `docs/project-synthesis`)
- **Testing:** `tests/` directory, pytest-based. Test fixtures in `tests/fixtures/`
- **Skills format:** Markdown files in `skills/` — OpenClaw skill format
- **SOP format:** YAML files in `sops/` — steps, approval gates, agent assignments
- **Workspace files:** Markdown in `docker/config/workspace/` — mounted into OpenClaw container
- **Travis's preferences:** Progressive disclosure, visual diagrams, one question at a time, quality over speed
