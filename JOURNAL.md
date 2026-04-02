# Engineering Journal — Digital Workforce Platform

## Current Phase: Phase 0 → Phase 1 Transition
## Current Task: Sprint complete — ready for integration testing
## Blocked On: Nothing

---

### Phase 0: Validate with Real Work
- [x] Task 0.1: Sign up for KiloClaw — DONE 2026-04-01
- [x] Task 0.2: Deploy OpenClaw instance — DONE 2026-04-01 (Frontier tier, Claude Opus 4.6)
- [x] Task 0.3: Connect to Slack workspace — DONE 2026-04-01 (Travis's personal workspace)
- [x] Task 0.3.1: Configure Leo identity and workspace files — DONE 2026-04-01
- [x] Task 0.3.2: Fix Gemini provider config (baseUrl + models required) — DONE 2026-04-01
- [x] Task 0.3.3: Generate and set Slack app icon — DONE 2026-04-01
- [x] Task 0.3.4: Verify Leo responds correctly via gateway CLI — DONE 2026-04-01
- [ ] Task 0.4: Give bot a real marketing task from active client — READY (BlackTie campaign fixture + skills ready)
- [ ] Task 0.5: Work with bot for several days, document findings — TODO
- [ ] Task 0.6: Identify first 2-3 workflows for SOPs — PARTIALLY DONE (ad-campaign SOP created from PoleBarnes/ad-campaign-agent patterns)
- [ ] Task 0.7: Test cron scheduling (daily check-in) — READY (cron configs written, need deployment)
- [ ] Task 0.8: Validate Slack as the right decision layer — TODO

### Sprint: Phase 0 Buildout — 2026-04-01
- [x] Task S.1: Create feature branch (sprint/phase0-buildout) — DONE 2026-04-01
- [x] Task S.2: Build OpenClaw skills framework (8 skills) — DONE 2026-04-01
- [x] Task S.3: Build ad-campaign SOP (YAML, 17 steps, 2 approval gates) — DONE 2026-04-01
- [x] Task S.4: Build landing-page SOP — DONE 2026-04-01
- [x] Task S.5: Build email-sequence SOP — DONE 2026-04-01
- [x] Task S.6: Create SOP template for new SOPs — DONE 2026-04-01
- [x] Task S.7: Implement LangGraph orchestrator with real Claude integration — DONE 2026-04-01
- [x] Task S.8: Implement context assembly (3-tier: platform → workspace → thread) — DONE 2026-04-01
- [x] Task S.9: Implement task routing (keyword + SOP matching + complexity heuristics) — DONE 2026-04-01
- [x] Task S.10: Implement SOP loader with workspace/platform search — DONE 2026-04-01
- [x] Task S.11: Implement Mechanic B with real Claude-powered quality analysis — DONE 2026-04-01
- [x] Task S.12: Implement SOP runner with real specialist dispatch — DONE 2026-04-01
- [x] Task S.13: Create BlackTie workspace (config, brand context, forms) — DONE 2026-04-01
- [x] Task S.14: Create workspace template for customer onboarding — DONE 2026-04-01
- [x] Task S.15: Security: enhanced exec-approvals.json — DONE 2026-04-01
- [x] Task S.16: Security: audit logging system (AuditLogger + secret patterns) — DONE 2026-04-01
- [x] Task S.17: Security: git pre-push hook for secret scanning — DONE 2026-04-01
- [x] Task S.18: Security: self-modification guard documentation — DONE 2026-04-01
- [x] Task S.19: Security: secret injection flow documentation — DONE 2026-04-01
- [x] Task S.20: Proactive: heartbeat cron config (2hr business hours) — DONE 2026-04-01
- [x] Task S.21: Proactive: morning briefing config — DONE 2026-04-01
- [x] Task S.22: Proactive: standing orders config (SOP detection, memory, health) — DONE 2026-04-01
- [x] Task S.23: Proactive: CRON.md workspace file for Leo — DONE 2026-04-01
- [x] Task S.24: Updated .gitignore — DONE 2026-04-01
- [x] Task S.25: Test suite written and executed — DONE 2026-04-01

### Sprint: Review & Fix — 2026-04-01
- [x] Task R.1: 9-reviewer code review (Architecture, Security, Code Quality, Content, Simplicity, Requirements, Spec Alignment, Codex-mini, GPT-5.4) — DONE
- [x] Task R.2: Repo restructure — eliminate platform/ stdlib collision, remove workspaces/ — DONE
- [ ] Task R.3: Fix critical bugs (approval gates, DAG wiring) — IN PROGRESS
- [ ] Task R.4: Fix high issues (context truncation, audit integration, security holes) — IN PROGRESS
- [ ] Task R.5: Fix remaining highs (skills loading, temperature, agent dispatch, feedback) — IN PROGRESS
- [ ] Task R.6: Consolidate duplicates, eliminate dead code — IN PROGRESS
- [ ] Task R.7: Add Mechanic C (Scout) + multi-agent experimentation docs — IN PROGRESS
- [ ] Task R.8: Fix REQUIREMENTS.md accuracy — TODO
- [ ] Task R.9: Full test suite re-run and validation — TODO

### Phase 1: LangGraph Integration
- [ ] Task 1.1: Set up LangGraph Cloud + LangSmith — TODO
- [ ] Task 1.2: Build first LangGraph workflow from most common manual task — TODO
- [ ] Task 1.3: Wire KiloClaw/OpenClaw to dispatch to LangGraph — TODO
- [ ] Task 1.4: Implement interrupt/resume for approval gates — TODO
- [ ] Task 1.5: Test multi-step task with 2+ approval gates — TODO
- [ ] Task 1.6: Set up git repo for all configuration — TODO

### Phase 2: Security & Secrets
- [ ] Task 2.1: Set up Doppler for secrets management — TODO
- [ ] Task 2.2: Migrate all API keys to vault — TODO
- [ ] Task 2.3: Implement secret injection flow — TODO
- [ ] Task 2.4: Set up git pre-push secret scanning — TODO
- [ ] Task 2.5: Configure exec-approvals.json — TODO
- [ ] Task 2.6: Implement audit logging — TODO

### Phase 3: First SOP + Web Form
- [ ] Task 3.1: Encode first proven workflow as formal SOP (YAML) — TODO
- [ ] Task 3.2: Build SOP-to-LangGraph-workflow pipeline — TODO
- [ ] Task 3.3: Build web intake form from SOP input schema — TODO
- [ ] Task 3.4: Deploy form to a URL — TODO
- [ ] Task 3.5: Test form submission → workflow execution → output delivery — TODO
- [ ] Task 3.6: Create second and third SOPs — TODO

### Phase 4: Mechanics
- [ ] Task 4.1: Implement Mechanic A (chat agent optimization) — TODO
- [ ] Task 4.2: Implement Mechanic B (workflow optimization) as final LangGraph node — TODO
- [ ] Task 4.3: Write both mechanic system prompts — TODO
- [ ] Task 4.4: Implement git diff output format — TODO
- [ ] Task 4.5: Wire proposals to admin channel with approval buttons — TODO
- [ ] Task 4.6: Test end-to-end mechanic flow — TODO

### Phase 5: Proactive Behavior
- [ ] Task 5.1: Implement heartbeat cron per project channel — TODO
- [ ] Task 5.2: Implement block surfacing with actionable notifications — TODO
- [ ] Task 5.3: Implement morning briefing — TODO
- [ ] Task 5.4: Implement project completion tracking — TODO
- [ ] Task 5.5: Implement multi-project prioritization — TODO

### Phase 6: Multi-Tenant & Scale
- [ ] Task 6.1: Set up second workspace for new customer — TODO
- [ ] Task 6.2: Implement per-workspace secret scoping — TODO
- [ ] Task 6.3: Test cross-workspace isolation — TODO
- [ ] Task 6.4: Implement two-layer update model — TODO
- [ ] Task 6.5: Implement Google Chat support — TODO
- [ ] Task 6.6: Implement Meta-Mechanic as weekly cron — TODO
- [ ] Task 6.7: Run all 16 acceptance criteria — TODO
- [ ] Task 6.8: Security audit — TODO

### Phase 7: Growth
- [ ] Task 7.1: Onboard customers 3-5 — TODO
- [ ] Task 7.2: Build SOP template library — TODO
- [ ] Task 7.3: Create customer onboarding automation — TODO
- [ ] Task 7.4: Begin scaling sales motion — TODO
- [ ] Task 7.5: Build operational dashboard — TODO

---

### Decisions Made
- 2026-04-01: Project initiated. Spec version 3.1 is sole source of truth.
- 2026-04-01: GitHub repo created at PoleBarnes/chat-force for platform code.
- 2026-04-01: KiloClaw Frontier tier selected (Claude Opus 4.6 as default model)
- 2026-04-01: Bot permissions set to "Ask for permission" (human approval required)
- 2026-04-01: Connected to Travis's personal Slack workspace via Socket Mode
- 2026-04-01: Model confirmed set to Claude Opus 4.6 in KiloClaw settings
- 2026-04-01: Slack pairing approved, bot responding in Slack DMs
- 2026-04-01: GitHub connected to KiloClaw (scoped to PoleBarnes/chat-force repo)
- 2026-04-01: Linear connected to KiloClaw
- 2026-04-01: Decided to move from KiloClaw hosted to self-hosted OpenClaw (reasons: full CLI access, OAuth token support for Max subscription, read-only config mounts, cost control)
- 2026-04-01: Self-hosted OpenClaw running in devcontainer via OrbStack on Mac Mini
- 2026-04-01: Doppler secrets management configured (SLACK_BOT_TOKEN, SLACK_APP_TOKEN, ANTHROPIC_AUTH_TOKEN, OPENCLAW_GATEWAY_TOKEN)
- 2026-04-01: OpenClaw 2026.4.1 gateway live, Slack socket mode connected, Claude Opus 4.6
- 2026-04-01: Gemini provider config fixed — requires baseUrl + models array (was missing, causing config validation failure)
- 2026-04-01: Leo identity configured — digital worker (not assistant), owns marketing/engineering/ops, SOP factory
- 2026-04-01: Workspace files pre-seeded (IDENTITY, SOUL, USER, AGENTS, TOOLS) — bypassed bootstrap ritual
- 2026-04-01: Slack app renamed to "Leo" with custom generated icon (Imagen 4.0)
- 2026-04-01: Gateway CLI (`openclaw agent --agent main --message "..."`) verified as test harness — bypasses Slack
- 2026-04-01: uv installed via brew for clean Python execution (replaces system pip3)
- 2026-04-01: Travis Dev Slack app created and deleted — Slack API always attaches bot_id to app tokens, can't send as user
- 2026-04-01: Skills implemented as markdown with YAML frontmatter — OpenClaw injects them into context when relevant triggers match
- 2026-04-01: Ad campaign SOP modeled after PoleBarnes/ad-campaign-agent (research→generate two-phase with approval gates)
- 2026-04-01: Using Anthropic SDK directly (not langchain-anthropic) for LLM calls in orchestrator — simpler, fewer dependencies
- 2026-04-01: Mechanic B uses Claude as LLM judge for quality scoring — scores against evaluation-criteria.yaml weights
- 2026-04-01: SOP runner implements graph caching to avoid re-parsing YAML on repeated calls
- 2026-04-01: Audit logger uses JSONL format (one JSON object per line) for easy streaming and analysis
- 2026-04-01: Secret patterns compiled as regex at module load time for performance
- 2026-04-01: BlackTie workspace configured as Tier 2 (direct Slack access) with agricultural market focus
- 2026-04-01: ARCHITECTURAL DECISION — Repo restructured: platform/ directory eliminated (Python stdlib collision). Children promoted to top-level (skills/, sops/, mechanics/, audit/, cron/, security/, docker/). exec-approvals.json moved into security/.
- 2026-04-01: ARCHITECTURAL DECISION — workspaces/ directory removed. Customer configuration is a deployment concern, not a repo concern. Each customer gets their own OpenClaw container with workspace files (IDENTITY, SOUL, USER, AGENTS, TOOLS, CONTEXT). Brand context configured at deployment time, not in the engine repo.
- 2026-04-01: ARCHITECTURAL DECISION — SOPs are platform-level templates, not per-customer. The same ad-campaign SOP works for any customer — brand context from the workspace customizes the output.
- 2026-04-01: INTEGRATION DECISION — Perplexity Computer added to Slack workspace as research agent. Leo (OpenClaw) stays as the single customer-facing orchestrator. Leo @mentions Perplexity in-thread when research steps fire. Multi-agent swarm is invisible to customer.
- 2026-04-01: NEW MECHANIC — Mechanic C "The Scout" defined. Daily/weekly research loop that scans for new tools, agents, and techniques. Proposes experiments. Reports integration readiness. Separate from Mechanic A (chat) and B (workflow).
- 2026-04-01: DESIGN PRINCIPLE — Multi-agent experimentation. Platform designed to plug in and swap different AI systems (Perplexity Computer, OpenClaw, Hermes, Factory Droids, future unknowns). Agent dispatch interface created (orchestrator/nodes/agents.py). Mechanics evaluate which agent performs best per step.
- 2026-04-01: 9-reviewer code review completed (7 Claude Opus + Codex-mini + GPT-5.4). Found 4 critical bugs, 11 high issues. All being fixed in this sprint.

### Questions for Human
- [PENDING] See Phase 0 questions batch below

### Blockers
- [ACTIVE] B1: Need answers to Phase 0 questions before starting work
- [ACTIVE] B2: Cannot access Linear issue TRA-213 (requires authentication)
