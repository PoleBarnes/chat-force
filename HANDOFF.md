# HANDOFF — Sprint Session

## Context

You are continuing work on the Digital Workforce Platform ("chat-force"). Read your memory files first, then these key files:

1. `Digital-Workforce-Platform-FINAL-v3.1.md` — the SOLE source of truth for requirements
2. `ORCHESTRATOR-PROMPT.md` — your operating instructions as build orchestrator
3. `JOURNAL.md` — engineering journal with current status and decisions

## What's Done (Phase 0 Infrastructure)

- OpenClaw self-hosted in devcontainer on Mac Mini (OrbStack)
- Doppler secrets management configured (project: chat-force, config: dev)
- Slack app "Leo" connected via socket mode, identity configured
- Leo's workspace files deployed (IDENTITY, SOUL, USER, AGENTS, TOOLS)
- Gateway CLI verified as test harness: `docker exec $CONTAINER_ID openclaw agent --agent main --message "..." --json`
- Gemini provider configured (Imagen 4.0 for image gen, Gemini models for text)
- uv installed for clean Python execution

## Your Mission: Massive Sprint

You are the **orchestrator**. You do NOT write code yourself. You plan, delegate to specialized sub-agents, review their output, and drive toward the Definition of Done.

### How to Work

1. **Read the spec** (`Digital-Workforce-Platform-FINAL-v3.1.md`) completely
2. **Read the journal** (`JOURNAL.md`) for current status
3. **Plan the sprint** — identify everything that can be built and tested right now
4. **Delegate aggressively** — spin up multiple specialized agents in parallel:
   - **Architect Agent** — system design, integration patterns, technical decisions
   - **Backend Agent** — Python/TypeScript code, LangGraph workflows, OpenClaw skills
   - **Infrastructure Agent** — Docker, deployment, CI/CD, config management
   - **Security Agent** — exec-approvals, secret injection, audit logging
   - **Testing Agent** — writes and runs tests, validates deliverables
   - **Documentation Agent** — JOURNAL.md updates, requirements tracking
5. **Test via gateway CLI** — verify Leo's behavior without Slack
6. **Update the journal** after each milestone

### What to Build (Priority Order)

**Immediate (can build now):**
- OpenClaw skills for Leo (marketing, code review, PR creation, research)
- Standing order enforcement (heartbeat, cron jobs)
- Memory management (daily logs, long-term memory curation)
- Git integration (PR workflows, code review patterns)

**Next (requires some design first):**
- LangGraph Cloud setup + first workflow
- OpenClaw → LangGraph dispatch pattern
- SOP detection logic (pattern recognition in task history)
- Mechanic A (chat optimization) system prompt

**Later (depends on above):**
- Mechanic B (workflow optimization)
- Web intake forms from SOP schemas
- Multi-tenant workspace isolation
- Google Chat support

### Key Constraints

- Claude Opus 4.6 is the primary LLM (via Anthropic auth token in Doppler)
- All secrets in Doppler — never hardcode
- All config in git — source-controlled, auditable
- Use `uv run --python 3.13 --with <deps>` for any Python work
- Test via `openclaw agent` CLI, not Slack
- Workspace templates live in `platform/docker/config/workspace/` — edit there, then copy to `~/.chat-force/openclaw/platform/docker/config/workspace/` for container access
- Travis prefers progressive disclosure, visual diagrams, one question at a time
- Quality over speed — get the architecture right

### Test Job Available

`tests/fixtures/blacktie-april-campaign.md` — a real BlackTie post-frame buildings April ad campaign. Use this to test Leo's marketing capabilities via the gateway CLI. **DO NOT deploy, push, or publish anything.**

`tests/fixtures/ad-campaign-workflow.md` — distilled ad campaign SOP from PoleBarnes/ad-campaign-agent. This is the workflow Leo should follow for campaigns. The full agent implementations (research + generation) are in that repo.

Reference repo: `PoleBarnes/ad-campaign-agent` — has research agent, generation agent, shared principles, templates, and skills. Use `gh api repos/PoleBarnes/ad-campaign-agent/contents/...` to read files.

Reference repo: `PoleBarnes/blacktie-marketing` — has previous BlackTie campaigns for reference.

### Safety Rules — CRITICAL

- **DO NOT push to main on any repo.** PoleBarnes/blacktie-marketing has Vercel on main.
- **Work on feature branches.** Commit locally, do not push unless to a feature branch.
- **DO NOT deploy anything externally.**
- **Test via gateway CLI only** — `openclaw agent --agent main --message "..."`, not Slack.
- When testing Leo with the campaign job, prefix with "TEST ONLY: Do not deploy or publish."
- Use `gh` CLI to read PoleBarnes repos (blacktie-marketing, ad-campaign-agent). Read-only.
- If something goes wrong, stop and contain. Don't try to fix forward on shared resources.

### SOP Evolution Strategy

SOPs start as **OpenClaw skills** (cheap to iterate) → promote to **LangGraph workflows** (rigid, verified) once proven.
- First implementation: skill with enforced steps
- After 3+ successful runs: propose promotion to LangGraph
- LangGraph workflows: defined states, phases, hard checks, approval gates
- LangGraph runs locally in the same devcontainer — no cloud needed for testing

### LangGraph Setup

Run LangGraph locally inside the existing OpenClaw devcontainer. Same container, separate process. No Docker-in-Docker, no cloud service. Install langgraph + dependencies, run locally for dev/test.

### Token Budget

Travis said burn tokens freely. Use as many agents as needed. Parallelize aggressively. Go deep on quality. This is a major sprint — do as much as you possibly can.

### When You're Done

Update `JOURNAL.md` with everything completed, decisions made, and what's next. Commit locally (do not push).
