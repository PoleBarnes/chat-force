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
- :red_circle: REQ-2.1: Humans are sole decision layer — no auto-apply changes
- :red_circle: REQ-2.2: Users only see one bot — swarm is hidden
- :red_circle: REQ-2.3: Every thread is a continuous conversation with full history
- :red_circle: REQ-2.4: Every task triggers mechanic analysis
- :red_circle: REQ-2.5: Default is no change — mechanics must prove improvement
- :red_circle: REQ-2.6: Security from day one
- :red_circle: REQ-2.7: Agent is proactive, not reactive
- :red_circle: REQ-2.8: All configuration in git
- :red_circle: REQ-2.9: Platform updates never break customer workflows (two-layer model)
- :red_circle: REQ-2.10: Use managed/hosted services first, self-host only when forced
- :red_circle: REQ-2.11: Claude is the primary LLM (Opus 4.6 complex, Sonnet 4.6 routine)

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
- :red_circle: REQ-5.1: KiloClaw deployed ($9/mo per instance)
- :red_circle: REQ-5.2: LangGraph Cloud configured (managed)
- :red_circle: REQ-5.3: LangSmith observability connected
- :red_circle: REQ-5.4: Kilo Gateway for model routing
- :red_circle: REQ-5.5: Anthropic Claude as primary LLM
- :red_circle: REQ-5.6: Git (GitHub private repos) for configuration
- :red_circle: REQ-5.7: Doppler for secrets management
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
- :red_circle: REQ-7.1: OpenClaw receives messages and interprets intent
- :red_circle: REQ-7.2: Routes simple tasks directly, complex tasks to LangGraph
- :red_circle: REQ-7.3: Recognizes SOP-matching tasks and triggers them
- :red_circle: REQ-7.4: Manages context across conversations
- :red_circle: REQ-7.5: Runs cron jobs for heartbeats, briefings, periodic checks
- :red_circle: REQ-7.6: Each client workspace gets own KiloClaw instance
- :red_circle: REQ-7.7: Self-modification prevention (prompt + exec-approvals.json)

## Section 8: Execution Layer (LangGraph)
- :red_circle: REQ-8.1: Workflows defined as graphs with nodes and edges
- :red_circle: REQ-8.2: Checkpointing after every node to Postgres
- :red_circle: REQ-8.3: Interrupt/resume for human approval gates
- :red_circle: REQ-8.4: Parallel execution for independent steps
- :red_circle: REQ-8.5: Thread history injected into every node's state
- :red_circle: REQ-8.6: LLM config — Opus 4.6 for complex/creative, Sonnet 4.6 for routine

## Section 9: OpenClaw + LangGraph Integration
- :red_circle: REQ-9.1: Routing decision logic (handle directly vs. dispatch)
- :red_circle: REQ-9.2: Communication flow — OpenClaw dispatches to LangGraph, formats responses
- :red_circle: REQ-9.3: LangGraph returns at interrupts, OpenClaw posts rich messages
- :red_circle: REQ-9.4: Resume flow — user response sent back to LangGraph

## Section 10: Proactive Agent Behavior
- :red_circle: REQ-10.1: Heartbeat cron per project channel (default every 2 hours business hours)
- :red_circle: REQ-10.2: Block surfacing with actionable notifications and buttons
- :red_circle: REQ-10.3: Morning briefing on presence or /checkin
- :red_circle: REQ-10.4: Project completion drive — auto-identify next step after approval

## Section 11: Context & Memory Architecture
- :red_circle: REQ-11.1: Platform Memory (global, git-backed, /platform/base-config.yaml)
- :red_circle: REQ-11.2: Workspace Memory (per-customer, git-backed)
- :red_circle: REQ-11.3: Thread Memory (ephemeral, fetched via API)
- :red_circle: REQ-11.4: Context assembly order: Platform → Workspace → Thread → Current input
- :red_circle: REQ-11.5: Token budget truncation for thread messages

## Section 12: SOPs & Workflow System
- :red_circle: REQ-12.1: SOPs emerge organically from repeated usage patterns
- :red_circle: REQ-12.2: SOPs defined as LangGraph workflows with verifiable outputs
- :red_circle: REQ-12.3: SOPs include human approval gates
- :red_circle: REQ-12.4: SOPs are customer-specific and frozen
- :red_circle: REQ-12.5: Each SOP has input schema for web form generation
- :red_circle: REQ-12.6: SOP-to-form pipeline (SOP → form → deploy → trigger workflow)
- :red_circle: REQ-12.7: At least 3 SOPs encoded as YAML with input schemas

## Section 13: Mechanics (Self-Improvement)
- :red_circle: REQ-13.1: Mechanic A — chat agent optimization (analyzes conversations)
- :red_circle: REQ-13.2: Mechanic B — workflow optimization (analyzes LangSmith traces)
- :red_circle: REQ-13.3: Both produce human-readable summary + git diff
- :red_circle: REQ-13.4: Proposals posted to admin channel with Approve/Reject/Edit buttons
- :red_circle: REQ-13.5: Approved proposals → git commit → config reload
- :red_circle: REQ-13.6: Rejected proposals → no change, logged for audit
- :red_circle: REQ-13.7: Golden rule — no change without evidence of improvement

## Section 14: Meta-Mechanic
- :red_circle: REQ-14.1: Runs weekly, reviews both mechanics' performance
- :red_circle: REQ-14.2: Proposes changes to mechanics' own prompts and eval criteria
- :red_circle: REQ-14.3: All Meta-Mechanic proposals require Travis approval

## Section 15: Secrets Management
- :red_circle: REQ-15.1: Secrets never appear in agent context
- :red_circle: REQ-15.2: Every secret scoped per-workspace, never cross-tenant
- :red_circle: REQ-15.3: Referenced by name, resolved at runtime (${secrets.KEY})
- :red_circle: REQ-15.4: All secret access audited
- :red_circle: REQ-15.5: Doppler vault with per-workspace environments
- :red_circle: REQ-15.6: Injection flow: Doppler → env vars at boot → resolved at tool call time
- :red_circle: REQ-15.7: Logs and traces scrubbed of secret patterns
- :red_circle: REQ-15.8: Git pre-push hooks scan for committed secrets

## Section 16: Security Architecture
- :red_circle: REQ-16.1: Ring 1 — KiloClaw managed infrastructure (VM, network, proxies)
- :red_circle: REQ-16.2: Ring 2 — Execution environment isolation (separate VMs, exec-approvals)
- :red_circle: REQ-16.3: Ring 3 — Application permissions (allowlists, vault, audit, prompt restrictions)
- :red_circle: REQ-16.4: Threat mitigations implemented for all listed threats

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
- :red_circle: REQ-21.1: Platform config repo structure (base-config, skills, tools, mechanics, audit)
- :red_circle: REQ-21.2: Per-workspace config structure (config, context, sops, skills, forms)
- :red_circle: REQ-21.3: LangGraph code repo structure (graphs, nodes, tools)

## Section 23: Multi-Agent Swarm
- :red_circle: REQ-23.1: SOP steps route to best available agent per step
- :red_circle: REQ-23.2: Agent types: OpenClaw, Perplexity, computer-use, Claude Code, API tools
- :red_circle: REQ-23.3: Each SOP step has agent field specifying handler
- :red_circle: REQ-23.4: Adding new agent types is a config change, not architecture change
- :red_circle: REQ-23.5: Start with OpenClaw for everything, add specialists when measurably needed
