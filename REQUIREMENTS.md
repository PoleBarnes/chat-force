# Requirements Tracker — Digital Workforce Platform

## Status Key
- :red_circle: NOT STARTED
- :yellow_circle: IN PROGRESS
- :green_circle: COMPLETE
- :pause_button: BLOCKED

---

## Section 1: Product Vision & Business Model
- :red_circle: REQ-1.1: System delivers outcomes through Slack/Google Chat/web forms
- :red_circle: REQ-1.2: Two service tiers (web form intake + direct Slack/GChat access)
- :red_circle: REQ-1.3: Self-learning system — SOPs emerge from repeated usage
- :red_circle: REQ-1.4: Managed service with Travis as admin
- :red_circle: REQ-1.5: Customer owns 100% of conversation history and outputs

## Section 2: Philosophy & Non-Negotiables
- :yellow_circle: REQ-2.1: Humans are sole decision layer — approval gates in graphs + mechanic approval interrupt added, but no runtime exec-approvals enforcement yet
- :yellow_circle: REQ-2.2: Users only see one bot — swarm is hidden (architecture supports this, pending Slack integration)
- :yellow_circle: REQ-2.3: Every thread is a continuous conversation with full history (context assembly implemented, needs Slack thread fetch)
- :yellow_circle: REQ-2.4: Every task triggers mechanic analysis — Mechanic B is final node in main graph, but untested end-to-end (requires API key)
- :green_circle: REQ-2.5: Default is no change — golden rule enforced in Mechanic B (scores < 0.7 triggers proposals, confidence >= 0.6 threshold)
- :yellow_circle: REQ-2.6: Security from day one — audit logger wired to orchestrator, exec-approvals defined, but no runtime command enforcement layer yet
- :yellow_circle: REQ-2.7: Agent is proactive, not reactive (cron configs written, pending deployment to OpenClaw)
- :green_circle: REQ-2.8: All configuration in git (all config is git-tracked YAML/MD)
- :yellow_circle: REQ-2.9: Platform updates never break customer workflows (two-layer model designed, not yet enforced at runtime)
- :green_circle: REQ-2.10: Use managed/hosted services first, self-host only when forced (using Doppler, OpenClaw)
- :green_circle: REQ-2.11: Claude is the primary LLM (Opus 4.6 complex, Sonnet 4.6 routine — hardcoded in orchestrator)

## Section 3: Service Tiers
- :red_circle: REQ-3.1: Tier 1 — web form intake, managed execution by Travis
- :red_circle: REQ-3.2: Tier 2 — direct Slack/Google Chat bot access with approval workflows
- :red_circle: REQ-3.3: Tier graduation path from Tier 1 to Tier 2

## Section 4: System Architecture
- :red_circle: REQ-4.1: Layer 1 — Interface (Slack, Google Chat, Web Forms)
- :red_circle: REQ-4.2: Layer 2 — Conversation & Routing (OpenClaw via KiloClaw)
- :red_circle: REQ-4.3: Layer 3 — Execution (LangGraph Workflows)
- :red_circle: REQ-4.4: Layer 4 — Mechanics (Self-Improvement)
- :red_circle: REQ-4.5: Two-layer update model (platform shared vs. customer frozen)
- :red_circle: REQ-4.6: Multi-tenant skill flywheel

## Section 5: Technology Stack
- :green_circle: REQ-5.1: KiloClaw deployed — self-hosted OpenClaw via devcontainer on Mac Mini
- :yellow_circle: REQ-5.2: LangGraph Cloud configured — local graphs built and compilable, cloud deploy pending
- :red_circle: REQ-5.3: LangSmith observability connected
- :green_circle: REQ-5.4: Kilo Gateway for model routing (Gemini + Claude configured)
- :green_circle: REQ-5.5: Anthropic Claude as primary LLM (Opus 4.6 + Sonnet 4.6 in orchestrator)
- :green_circle: REQ-5.6: Git (GitHub private repos) for configuration
- :green_circle: REQ-5.7: Doppler for secrets management (project: chat-force, config: dev)
- :red_circle: REQ-5.8: Web forms via Next.js on Vercel (or similar)

## Section 6: Interface Layer
- :red_circle: REQ-6.1: Slack workspace structure (client channels, admin, briefings, approvals)
- :red_circle: REQ-6.2: Google Chat support with equivalent core functionality
- :red_circle: REQ-6.3: Web intake forms auto-generated from SOP input schemas
- :red_circle: REQ-6.4: Progressive disclosure — plan preview before execution
- :red_circle: REQ-6.5: Approval flow with Approve/Reject/Edit/Re-run buttons (Block Kit / Cards)
- :red_circle: REQ-6.6: Morning briefing on presence detection or /checkin
- :red_circle: REQ-6.7: Human memory control — deleting messages removes from context

## Section 7: Conversation & Routing Layer (OpenClaw)
- :yellow_circle: REQ-7.1: OpenClaw receives messages — gateway CLI verified, but orchestrator not yet connected to OpenClaw
- :yellow_circle: REQ-7.2: Routing logic implemented (routing.py), but not wired to OpenClaw — standalone Python module
- :yellow_circle: REQ-7.3: SOP matching implemented (sop_loader.py), but not connected to OpenClaw dispatch
- :yellow_circle: REQ-7.4: Context assembly implemented (context.py with skills loading + token budget), needs Slack thread fetch
- :yellow_circle: REQ-7.5: Runs cron jobs — configs written, pending deployment to OpenClaw
- :yellow_circle: REQ-7.6: Each client workspace gets own OpenClaw instance — single instance running
- :yellow_circle: REQ-7.7: Self-modification prevention — exec-approvals defined + shell metacharacters blocked, but no runtime enforcement code

## Section 8: Execution Layer (LangGraph)
- :green_circle: REQ-8.1: Workflows defined as graphs with nodes and edges (main, mechanic_b, sop_runner graphs)
- :yellow_circle: REQ-8.2: Checkpointing after every node to Postgres (LangGraph handles this, needs Postgres for persistence)
- :green_circle: REQ-8.3: Interrupt/resume for human approval gates — interrupt_before on preview, deliverable, and mechanic approval nodes + SOP approval gates pause execution
- :green_circle: REQ-8.4: Parallel execution — SOP runner builds DAG from depends_on, enabling parallel step execution
- :yellow_circle: REQ-8.5: Thread history injected via context assembly — works when thread_messages provided, no Slack fetch yet
- :green_circle: REQ-8.6: LLM config — Opus 4.6 for complex/creative, Sonnet 4.6 for routine, temperature 0.7 for creative read from config

## Section 9: OpenClaw + LangGraph Integration
- :green_circle: REQ-9.1: Routing decision logic (handle directly vs. dispatch) — routing.py implemented
- :yellow_circle: REQ-9.2: Communication flow — dispatch logic built, needs OpenClaw-to-LangGraph HTTP bridge
- :yellow_circle: REQ-9.3: LangGraph returns at interrupts, OpenClaw posts rich messages — interrupt architecture ready, needs Slack formatting
- :yellow_circle: REQ-9.4: Resume flow — graph supports resume, needs interface layer wiring

## Section 10: Proactive Agent Behavior
- :yellow_circle: REQ-10.1: Heartbeat cron per project channel — config written (heartbeat.yaml + CRON.md), pending deployment
- :yellow_circle: REQ-10.2: Block surfacing with actionable notifications — specified in CRON.md, pending Slack Block Kit implementation
- :yellow_circle: REQ-10.3: Morning briefing on presence or /checkin — config written (morning-briefing.yaml), pending deployment
- :yellow_circle: REQ-10.4: Project completion drive — specified in standing-orders.yaml, pending implementation

## Section 11: Context & Memory Architecture
- :green_circle: REQ-11.1: Platform Memory (global, git-backed, /base-config.yaml) — implemented
- :yellow_circle: REQ-11.2: Workspace Memory — customer config is a deployment concern (OpenClaw workspace files), not in repo. Brand context provided at deploy time.
- :yellow_circle: REQ-11.3: Thread Memory (ephemeral, fetched via API) — context.py accepts thread messages, needs Slack API fetch
- :green_circle: REQ-11.4: Context assembly order: Platform → Workspace → Thread → Current input — implemented in context.py
- :green_circle: REQ-11.5: Token budget truncation for thread messages — implemented with oldest-first truncation

## Section 12: SOPs & Workflow System
- :yellow_circle: REQ-12.1: SOPs emerge organically from repeated usage patterns — sop-detection skill written, needs runtime testing
- :green_circle: REQ-12.2: SOPs defined as LangGraph workflows — sop_runner.py generates DAG from YAML with proper depends_on wiring
- :green_circle: REQ-12.3: SOPs include human approval gates — ad-campaign has 2 gates with conditional routing (approve/reject)
- :green_circle: REQ-12.4: SOPs are platform-level templates — customer context customizes output at deployment time
- :green_circle: REQ-12.5: Each SOP has input schema for web form generation — ad-campaign has 11-field input_schema
- :yellow_circle: REQ-12.6: SOP-to-form pipeline — form config written (ad-campaign-form.yaml), web app pending
- :green_circle: REQ-12.7: At least 3 SOPs encoded as YAML — ad-campaign, landing-page, email-sequence

## Section 13: Mechanics (Self-Improvement)
- :yellow_circle: REQ-13.1: Mechanic A — prompt written, needs runtime integration as OpenClaw skill
- :yellow_circle: REQ-13.2: Mechanic B — LangGraph sub-graph with Claude-powered scoring, but trace data is placeholder (needs LangSmith)
- :yellow_circle: REQ-13.3: Mechanic B produces summary + diffs. Mechanic A is prompt-only (no code)
- :yellow_circle: REQ-13.4: Proposals posted to admin channel — format ready, needs Slack Block Kit integration
- :yellow_circle: REQ-13.5: Approved proposals → git commit → config reload — workflow designed, needs automation
- :yellow_circle: REQ-13.6: Rejected proposals → no change, logged for audit — audit logger ready, needs integration
- :green_circle: REQ-13.7: Golden rule enforced — scores < 0.7 triggers proposals, confidence >= 0.6 threshold, evidence required

## Section 14: Meta-Mechanic
- :red_circle: REQ-14.1: Runs weekly, reviews both mechanics' performance
- :red_circle: REQ-14.2: Proposes changes to mechanics' own prompts and eval criteria
- :red_circle: REQ-14.3: All Meta-Mechanic proposals require Travis approval

## Section 15: Secrets Management
- :green_circle: REQ-15.1: Secrets never appear in agent context — llm.py reads from os.environ, never passes to prompts
- :yellow_circle: REQ-15.2: Every secret scoped per-workspace — Doppler config supports this, single workspace for now
- :yellow_circle: REQ-15.3: Secret reference pattern designed (${secrets.KEY}), but tools.yaml is deleted — pattern not yet used in practice
- :green_circle: REQ-15.4: All secret access audited — AuditLogger.log_secret_access() implemented
- :green_circle: REQ-15.5: Doppler vault with per-workspace environments — configured (chat-force/dev)
- :green_circle: REQ-15.6: Injection flow documented and implemented — secret-injection.md + llm.py
- :green_circle: REQ-15.7: Logs and traces scrubbed of secret patterns — audit_logger._scrub_secrets() + secret_patterns.py
- :green_circle: REQ-15.8: Git pre-push hooks scan for committed secrets — scripts/git-pre-push-hook.sh

## Section 16: Security Architecture
- :green_circle: REQ-16.1: Ring 1 — OpenClaw in devcontainer (OrbStack) with managed networking
- :yellow_circle: REQ-16.2: Ring 2 — exec-approvals.json defined with allowlist + shell metacharacter blocking, but no runtime enforcement code
- :yellow_circle: REQ-16.3: Ring 3 — Doppler configured, audit logger wired to LLM calls, prompt restrictions defined, but enforcement is config-only
- :yellow_circle: REQ-16.4: Threat mitigations — most implemented, network allowlists pending

## Section 17: Observability, Circuit Breakers & Cost Control
- :red_circle: REQ-17.1: Per-task token budget (default 100k)
- :red_circle: REQ-17.2: Per-task time limit (default 30 min)
- :red_circle: REQ-17.3: Circuit breakers (token rate, error rate, daily cost, deploy rate)
- :red_circle: REQ-17.4: Health indicators (bot status, context usage, /status command)
- :red_circle: REQ-17.5: LangSmith traces for every run

## Section 18: Acceptance Criteria (16 tests)
- :red_circle: AC-1: Slack task → plan preview → approval → execution → delivery in-thread
- :red_circle: AC-2: Same flow in Google Chat
- :red_circle: AC-3: Reply "no" → agent revises → re-presents
- :red_circle: AC-4: Mechanic B posts reflection with scores and proposals after task
- :red_circle: AC-5: Approve mechanic proposal → git diff committed → next run uses improved config
- :red_circle: AC-6: Reject proposal → config unchanged → no git commit
- :red_circle: AC-7: Kill mid-task → restart → graph resumes from checkpoint
- :red_circle: AC-8: Second task in same thread 24 hours later → all prior context present
- :red_circle: AC-9: Auto config change without approval → system blocks it
- :red_circle: AC-10: Git revert → next run uses previous config
- :red_circle: AC-11: Workspace A cannot access Workspace B's secrets
- :red_circle: AC-12: Web form submission triggers LangGraph workflow correctly
- :red_circle: AC-13: Heartbeat fires on schedule, agent reports status
- :red_circle: AC-14: Agent blocked → actionable DM with options and buttons
- :red_circle: AC-15: Morning briefing triggers on presence or /checkin
- :red_circle: AC-16: All LLM calls use Claude (verified via LangSmith)

## Section 21: Repository Structure
- :green_circle: REQ-21.1: Platform config repo structure — base-config.yaml, skills/, tools.yaml, mechanics/, audit/, cron/, security/
- :green_circle: REQ-21.2: Per-workspace config structure — docker/config/workspace/{id}/ with config.yaml, context.md (deployment concern, not in repo)
- :green_circle: REQ-21.3: LangGraph code repo structure — orchestrator/ with graphs/, nodes/, langgraph.json, requirements.txt

## Section 23: Multi-Agent Swarm
- :yellow_circle: REQ-23.1: Agent dispatch interface built (orchestrator/nodes/agents.py) — routes by agent field, but non-Claude agents fall back to Claude
- :yellow_circle: REQ-23.2: Agent types — OpenClaw implemented, Perplexity/Claude Code have stubs that fall back to Claude
- :green_circle: REQ-23.3: Each SOP step has agent field specifying handler — ad-campaign SOP uses openclaw, api:gemini, api:imagemagick, claude_code
- :green_circle: REQ-23.4: Adding new agent types is a registry addition — agents.py uses @register_agent decorator pattern
- :green_circle: REQ-23.5: Start with OpenClaw for everything — all current SOPs use openclaw as primary specialist
