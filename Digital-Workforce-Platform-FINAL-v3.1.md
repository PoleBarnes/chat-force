# DIGITAL WORKFORCE PLATFORM — Complete Product & Build Specification

**Version:** 3.0 — Final Merged Design
**Date:** March 31, 2026
**Owner:** Travis
**Status:** Ready for implementation

---

> **CRITICAL: READ BEFORE BUILDING**
>
> This is the SOLE source of truth. It merges product vision, business model,
> technical architecture, and implementation plan from multiple design sessions.
> The conversations that produced it are not available to you.
>
> If something is ambiguous, ASK TRAVIS. Do not invent requirements.
> Do not skip security sections. Build in the order specified in Section 17.

---

## Table of Contents

1. Product Vision & Business Model
2. Philosophy & Non-Negotiables
3. Service Tiers & Customer Experience
4. System Architecture Overview
5. Technology Stack
6. Interface Layer: Slack, Google Chat & Web Forms
7. Conversation & Routing Layer: OpenClaw via KiloClaw
8. Execution Layer: LangGraph Workflows
9. OpenClaw + LangGraph Integration
10. Proactive Agent Behavior
11. Context & Memory Architecture
12. SOPs & Workflow System
13. The Mechanics: Self-Improvement Engines
14. The Meta-Mechanic
15. Secrets Management & Authentication
16. Security Architecture
17. Observability, Circuit Breakers & Cost Control
18. Quality Gates, Metrics & Acceptance Criteria
19. Go-to-Market Strategy
20. Build Order & Implementation Phases
21. Repository & Configuration Structure
22. Key Design Decisions & Rationale
23. Multi-Agent Swarm: Specialized Agents Per Step

---

## 1. Product Vision & Business Model

### 1.1 What This Is

A managed digital workforce delivered as a service. Businesses get an AI-powered team that handles repeatable operational tasks — starting with marketing campaigns — through familiar interfaces (Slack, Google Chat, or web forms). The system self-learns from usage, evolves standard operating procedures organically, and improves continuously through automated mechanic agents. The customer never touches infrastructure, manages API keys, or learns new tools. They describe what they want and get outcomes.

### 1.2 Core Value Proposition

**Outcome-based service:** Customers pay a flat retainer for results, not access to software. They are buying a workforce, not a tool. A single marketing coordinator costs $4,000–$5,000/month minimum. The digital workforce handles 60%+ of repetitive coordination work at lower cost, 24/7, with compounding improvement.

**Zero-friction interface:** Slack or Google Chat is the control plane. No new logins, no dashboards to learn. Or for simpler engagements: a branded web form. Fill it out, get deliverables. The digital workforce lives where the team already works — or behind a form so simple anyone can use it.

**Self-learning system:** The workforce gets better the more it is used. Repeated patterns are detected and crystallized into SOPs automatically. After 50 tasks, 15–20 proven improvements tailored to the specific business. After 200 tasks, deeply specialized.

**Managed service with human admin:** Travis serves as the digital workforce administrator — handling security, upgrades, optimization, and troubleshooting. Each customer has a dedicated AI team manager.

### 1.3 Key Differentiators

- No adoption barrier — Slack/Google Chat already in use, or web forms require zero onboarding
- SOPs emerge from usage rather than requiring upfront process documentation
- Multi-tenant architecture where every customer benefits from platform-wide skill improvements
- Human-gated deployments and changes ensure quality and safety
- Self-improvement loop: no competitor has an automated mechanic that reviews every run and proposes config improvements as git diffs
- Switching costs are naturally high due to accumulated learned workflows, without being predatory

### 1.4 Pricing Model

| Tier | Price | What Customer Gets |
|------|-------|--------------------|
| Starter | $1,500/mo | Web form intake. Managed execution. Travis runs the system on their behalf. |
| Standard | $3,000/mo | Slack/Google Chat access. Direct bot interaction. Approval workflows. Morning briefings. |
| Enterprise | $5,000–$8,000/mo | Full workspace. Custom SOPs. Priority support. Advanced integrations. |
| Project-based | $2,000–$10,000 per project | Websites, campaigns, automations. Delivered by AI, managed by Travis. |

### 1.5 Data Ownership

- Customers own 100% of conversation history and all produced artifacts
- Customers receive copies of all outputs
- The execution layer, platform infrastructure, and mechanic system are Travis's intellectual property
- Clear contractual separation between customer data/outputs and platform IP

### 1.6 Unit Economics

- Infrastructure cost per workspace: ~$30–$50/month (KiloClaw + LangGraph Cloud + secrets)
- LLM API costs: $50–$200/month per active workspace (varies by usage)
- Gross margin: 70–85% at Standard tier
- Every new customer makes the system smarter (shared skill improvements)
- Every system improvement makes every customer happier (flywheel effect)
- Margin expands over time as automation replaces manual effort

---

## 2. Philosophy & Non-Negotiables

1. **We sell outcomes, not tools.** The customer buys a workforce. The technology is invisible.

2. **Humans are the sole decision layer.** No change to agent config, tools, skills, SOPs, or deployable code ever happens without explicit human approval. The Mechanic proposes; the human disposes.

3. **The sausage-making is hidden.** Users only ever talk to one bot (or fill out a form). They never see the swarm, the orchestration graph, the tool calls, or the infrastructure.

4. **Every thread is a continuous conversation.** Full thread history is injected on every invocation. The system never loses context. If the user deletes a message, it disappears from future context.

5. **Every task makes the system better.** After every task, mechanics analyze what happened and propose improvements. Most find nothing — that's fine. Over time, proven improvements compound.

6. **If you can't prove it's better, change nothing.** The mechanic's default is always no change. Configuration drift is the enemy.

7. **Security from day one.** Proprietary client data. Defense in depth. Multiple containment layers.

8. **The agent is proactive, not reactive.** It drives projects toward completion, surfacing blocks to humans only when stuck. The human's job is to unblock and approve.

9. **Configuration lives in git.** All config, skills, SOPs, and tool definitions are version-controlled. Mechanic changes become git diffs. Approval = merge. Rejection = no change. Breakages = git revert.

10. **Platform updates never break customer workflows.** Two-layer update model: platform-wide improvements are shared and deploy OFF by default. Customer-specific SOPs are frozen and only change when the customer chooses.

11. **Start managed, vertically integrate later.** Use hosted/managed versions of everything. Only self-host when a concrete limitation forces it.

12. **Slack is the hypothesis.** Phase 0 validates that Slack/Google Chat threads are the right human harness. If not, we pivot early.

13. **Claude is the primary LLM.** Opus 4.6 for complex tasks, Sonnet 4.6 for routine. Temperature 0.0 for mechanic/reflection, 0.7 for creative tasks.

---

## 3. Service Tiers & Customer Experience

### 3.1 Tier 1: Managed Execution (Web Forms)

**The customer never sees Slack.** They interact through branded web intake forms.

**Customer experience:**
1. Customer goes to a URL (e.g., campaigns.yourcompany.com)
2. Selects a service type (e.g., "Ad Campaign," "Landing Page," "Email Sequence")
3. Fills out a structured form with the inputs that SOP requires
4. Submits. Receives confirmation.
5. Travis receives the submission, reviews it, refines if needed, feeds it into the system
6. The system runs — potentially through multiple iterations internally
7. Customer receives polished deliverables (via email, shared drive, or a results portal)

**Why this tier exists:** Lower barrier to entry. Any business understands "fill out a form, get results." No Slack setup, no bot adoption, no behavior change. Also allows Travis to iterate internally — the customer doesn't see failed attempts or rough drafts.

**Technical implementation:** Each SOP defines its required inputs. A web form is auto-generated (or manually built) from the SOP's input schema. Form submission triggers the LangGraph workflow with those inputs. Travis reviews outputs before delivery.

### 3.2 Tier 2: Direct Access (Slack / Google Chat)

**The customer talks directly to the bot in their workspace.**

**Customer experience:**
1. Customer adds the Slack app to their workspace (or Google Chat equivalent) — that IS the onboarding
2. Bot appears in their workspace immediately
3. Customer describes tasks in threaded conversations
4. Bot shows progressive previews, asks for approval at each stage
5. Customer approves or rejects with buttons/reactions
6. Deliverables are posted in-thread
7. Morning briefings surface what needs attention
8. SOPs emerge organically from repeated tasks

**Why this tier exists:** More powerful experience. Faster turnaround (no Travis relay). Customer has direct control and visibility. Better for customers who want to actively steer their workforce.

**The Slack app IS the product packaging.** No software to install, no infrastructure to configure. Updates push from Travis's end — customers receive upgrades seamlessly. Five-minute onboarding.

### 3.3 Tier Graduation

Customers start on Tier 1. As the system matures for their specific work (SOPs proven, workflows reliable), Travis offers Tier 2 as an upgrade. The underlying system is identical — same LangGraph workflows, same OpenClaw agent, same mechanics. The only difference is who talks to it.

---

## 4. System Architecture Overview

### Four Layers

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: INTERFACE                                          │
│  Slack • Google Chat • Web Intake Forms                      │
│  The only things customers ever see                          │
├─────────────────────────────────────────────────────────────┤
│  LAYER 2: CONVERSATION & ROUTING (OpenClaw via KiloClaw)     │
│  Intent interpretation • Task routing • Simple task execution│
│  Session management • Cron • Presence detection              │
├─────────────────────────────────────────────────────────────┤
│  LAYER 3: EXECUTION (LangGraph Workflows)                    │
│  Structured SOPs • Multi-step orchestration • Checkpointing  │
│  Human approval gates • Parallel agent execution             │
├─────────────────────────────────────────────────────────────┤
│  LAYER 4: MECHANICS (Self-Improvement)                       │
│  Mechanic A: Chat agent optimization                         │
│  Mechanic B: Workflow execution optimization                 │
│  Meta-Mechanic: Improves the mechanics themselves            │
│  All changes human-gated, git-versioned                      │
└─────────────────────────────────────────────────────────────┘
```

### Two-Layer Update Model

**Platform Layer (Shared, Travis-Controlled):**
Skills, model upgrades, new capabilities, performance improvements. Moves on Travis's schedule. Tested in staging before production. Every client benefits. New capabilities deploy OFF by default. Similar to OS kernel updates — patches are tested, staged, rolled out.

**Customer Layer (Frozen, Customer-Controlled):**
SOPs and workflow definitions are customer-specific. These only change when the customer chooses. New platform features are available but don't modify existing workflows. Customers opt-in to new capabilities. Existing production workflows are never broken by platform updates.

### Multi-Tenant Skill Flywheel

When Client A needs video generation, Travis builds that skill. Now ALL clients have access to it (as an opt-in capability). Every new capability is amortized across the entire customer base. The cost of development decreases per-customer as the customer base grows. Every customer makes the platform smarter.

---

## 5. Technology Stack

### Core Infrastructure

| Component | Technology | Why |
|-----------|-----------|-----|
| Chat integration | **KiloClaw** ($9/mo per instance) | Managed OpenClaw. Auto-restart, security proxies, 50+ platforms, cron, persistent memory. Zero ops. |
| Task orchestration | **LangGraph Cloud** (managed) | State machine with checkpointing, interrupt/resume, parallel execution. Usage-based pricing. |
| Observability | **LangSmith** | Structured traces of every LLM call and tool invocation. The mechanics' eyes. |
| AI model routing | **Kilo Gateway** (included with KiloClaw) | 500+ models at zero markup. BYOK API keys. |
| Primary LLM | **Anthropic Claude** (Opus 4.6 / Sonnet 4.6) | All reasoning and tool-calling. |
| Configuration | **Git** (GitHub private repos) | Source of truth. YAML for machine config, Markdown for human docs. |
| Secrets | **Doppler** (managed, free tier to start) | Centralized, encrypted, auto-rotatable. Never in code or agent context. |
| Web forms | **Simple web app** (Next.js on Vercel or similar) | Auto-generated from SOP input schemas. Triggers LangGraph workflows. |

### Why KiloClaw First

KiloClaw at $9/month per instance provides: one-click deploy, auto-restart, managed security, automatic OpenClaw updates, 500+ models, persistent memory, cron scheduling, and multi-platform chat. The escape hatch to self-hosted OpenClaw exists if needed — same code, same config, transfers directly.

**Cost for 5 workspaces:** 5 × $9 + LangGraph Cloud ~$50-100 + Doppler free = ~$100-150/month infrastructure before LLM API costs.

### Why LangGraph Cloud

Managed Postgres checkpointing, webhook handling, graph deployment via git push, scaling. $0.001 per node execution + standby time. Requires LangSmith Plus at $39/user/month. Eliminates need to manage Postgres, webhook servers, and deployment pipeline.

---

## 6. Interface Layer: Slack, Google Chat & Web Forms

### Slack Workspace Structure (Tier 2 Customers)

- **client-[name]-marketing** — department channels where the customer works
- **client-[name]-campaigns-[month]** — campaign-specific channels
- **client-[name]-admin** — private admin channel (Travis + mechanics only, not visible to customer)
- **#briefings** — morning briefings, status summaries
- **#approvals** — deployment gates with approve/reject buttons

### Google Chat (Tier 2 Customers)

Same structure using Google Chat Spaces. Cards API for approval workflows. Slightly less rich than Slack Block Kit but core functionality identical.

### Web Intake Forms (Tier 1 Customers)

Each SOP defines its required inputs as a schema. Forms are generated from this schema:

```yaml
# In the SOP definition
inputs:
  - name: product_description
    type: text
    required: true
    label: "Describe your product or service"
  - name: target_audience
    type: text
    required: true
    label: "Who is your ideal customer?"
  - name: budget_range
    type: select
    options: ["$500-1000", "$1000-2500", "$2500-5000", "$5000+"]
    label: "Monthly ad budget"
  - name: tone
    type: select
    options: ["Professional", "Casual", "Bold", "Luxury"]
    label: "Brand tone"
  - name: reference_images
    type: file_upload
    required: false
    label: "Upload any brand images or references"
```

Form submission triggers the LangGraph workflow. Travis reviews results before delivery to customer.

### Interaction Patterns

**Progressive disclosure:** When a customer describes a task, the agent doesn't immediately execute. It presents a brief plan first. If agreed, next level of detail. At each stage the customer can correct course. Prevents the most expensive failure: building the wrong thing confidently.

**Approval flow:** Deliverables are posted with Approve/Reject/Edit/Re-run buttons (Slack Block Kit or Google Chat Cards). Nothing ships without explicit human yes.

**Morning briefing (Tier 2):** When the customer becomes active, agent posts: blocked items needing decisions, approvals waiting, work completed overnight, upcoming work, system health.

**Human memory control:** Deleting a message removes it from future context. Direct editorial control.

---

## 7. Conversation & Routing Layer: OpenClaw via KiloClaw

### Role

OpenClaw is the conversational front-end. It receives all user input, interprets intent, and routes work:

- Simple tasks (research, Q&A, exploration): handles directly using built-in capabilities
- Complex multi-step tasks: routes to LangGraph workflows
- SOP-matching tasks: recognizes when a defined SOP applies and triggers it
- Helps users create and refine SOPs through conversation
- Manages context across conversations
- Runs cron jobs for heartbeats, briefings, and periodic checks

### Deployment

Each client workspace gets its own KiloClaw instance ($9/month). Configuration is git-backed. OpenClaw cannot modify its own config at runtime (prompt-level restriction + exec-approvals.json). When it wants a config change, it writes a mechanic request note. Mechanic A picks it up.

### Self-Modification Prevention

OpenClaw's config is managed via git and the KiloClaw dashboard. The agent is instructed: "Never modify files in /config. If you need a configuration change, write a request to /workspace/mechanic-requests/ describing what you need and why. Mechanic A will evaluate it." The exec-approvals.json allowlist restricts which commands can run.

If prompt-level restrictions prove insufficient (agent repeatedly violates them), that's the trigger to migrate to self-hosted OpenClaw with filesystem-level read-only config mounts.

---

## 8. Execution Layer: LangGraph Workflows

### Role

LangGraph handles all structured, multi-step work. This is where SOPs are executed.

- Workflows defined as graphs with nodes (steps) and edges (transitions)
- Checkpointing after every node to Postgres (crash recovery, time-travel debugging)
- Interrupt/resume for human approval gates
- Parallel execution for independent steps
- Thread history injected into every node's state

### Graph Structure

```
User Input (from Slack, Google Chat, or Web Form)
    │
    ▼
[Entry Node] — Parse input, load context, match SOP if applicable
    │
    ▼
[Planner Node] — Create task breakdown (or load SOP steps)
    │
    ▼
[INTERRUPT: Preview] — Show plan, wait for approval
    │
    ▼ (on approval)
[Execution Nodes] — Parallel or sequential specialist work
    │
    ▼
[INTERRUPT: Preview] — Show deliverables for review
    │
    ▼ (on approval)
[Finalization Node] — Package outputs, deploy if applicable
    │
    ▼
[Mechanic B Node] — Analyze execution, propose improvements
    │
    ▼
[INTERRUPT: Mechanic Approval] — Show improvement proposals
    │
    ▼
[End] — Store state, update project memory
```

### LLM Configuration

- Creative/generative tasks: Claude Opus 4.6, temperature 0.7
- Planning/analysis: Claude Opus 4.6, temperature 0.0
- Mechanic/reflection: Claude Opus 4.6, temperature 0.0
- Routine/simple: Claude Sonnet 4.6, temperature 0.0 (cost optimization)

---

## 9. OpenClaw + LangGraph Integration

### Routing Decision

OpenClaw decides for every incoming message:

**Handle directly:** Simple questions, research, exploration, brainstorming, status checks, one-off tasks without approval gates.

**Dispatch to LangGraph:** Multi-step tasks with deliverables, tasks matching a defined SOP, anything requiring deployment approval, tasks involving multiple specialist agents, tasks explicitly scoped as projects.

### Communication Flow

1. User posts message (Slack/Google Chat) or submits web form
2. OpenClaw receives, fetches thread history (if applicable)
3. OpenClaw decides: handle directly or dispatch to LangGraph
4. If dispatching: calls LangGraph Cloud API with task, history, thread_id, project config
5. LangGraph runs. At each interrupt, returns response to OpenClaw
6. OpenClaw formats as rich chat message (buttons, images) and posts to thread (or queues for Travis review if Tier 1)
7. User responds
8. OpenClaw sends response back to LangGraph to resume
9. Repeat until complete
10. Mechanic B runs as final step

---

## 10. Proactive Agent Behavior

The agent is NOT reactive. It drives projects toward completion autonomously.

### Heartbeat Cron Jobs (Tier 2 Customers)

Every project channel has a heartbeat (default: every 2 hours during business hours). On each heartbeat:

1. **Can I work without human input?** If yes: do it. Post status update.
2. **Am I blocked?** If yes: send actionable notification with options and buttons. Don't re-notify if already waiting.
3. **Nothing to do?** Report status. Ready for new work.
4. **Anything changed since last check?** Process new messages immediately.

### Block Surfacing

Notifications must be actionable. Not "I'm stuck" but "Q2 campaign: two headline options. A emphasizes price. B emphasizes quality. [Button A] [Button B] [Button: Both]."

### Morning Briefing

When human becomes active or runs /checkin:
1. Blocked items needing decisions (with response buttons)
2. Approvals waiting
3. Work completed overnight
4. Upcoming work
5. System health

### Project Completion Drive

The agent tracks overall goal, completed tasks, remaining tasks, next logical step. When a task is approved, it identifies the next step, confirms plan, and proceeds. Default behavior is forward momentum. Human can override anytime.

---

## 11. Context & Memory Architecture

### Three-Tier Memory

**Tier 1: Platform Memory (Global, all workspaces)**
- Stored in: git repo at `/platform/base-config.yaml`
- Contains: Universal skills, shared tool configs, platform-wide learnings
- Updated by: Travis only. Deployed to all workspaces OFF by default.
- This is the shared skill flywheel. When a new skill is proven, all clients can opt in.

**Tier 2: Workspace Memory (Durable, per-customer)**
- Stored in: git repo at `/workspaces/{client}/config.yaml` and `/workspaces/{client}/context.md`
- Contains: Client brand guidelines, approved SOPs, tool preferences, accumulated learnings
- Updated by: Mechanics with appropriate approval (auto for low-risk, Travis-approved for significant changes)

**Tier 3: Thread Memory (Ephemeral, per-conversation)**
- Stored in: Chat thread messages (fetched via API at invocation time)
- Contains: Live conversation, recent decisions, current task context
- Updated by: User posting or deleting messages

### Context Assembly

1. Load Platform Memory (universal skills, shared config)
2. Overlay Workspace Memory (client-specific config, SOPs, brand guidelines)
3. Append Thread Memory (last N messages, default 50 or token budget)
4. Append current input (new message or form submission)
5. Truncate oldest thread messages if over token budget

---

## 12. SOPs & Workflow System

### Organic SOP Evolution

SOPs are NOT built upfront. They emerge from usage:

1. Customer performs a task (e.g., runs an ad campaign)
2. Customer performs a similar task again
3. System detects the pattern: "This looks like the previous task"
4. System suggests in Slack: "We've done this type of task twice. Let's build a procedure for it."
5. SOP is collaboratively refined through conversation — customer and agent work together
6. SOP is encoded as a LangGraph workflow with structured steps and verifiable outputs
7. Future instances are automatically routed through the SOP
8. **A web intake form is auto-generated from the SOP's input schema** — enabling Tier 1 delivery

### SOP Characteristics

- Defined as LangGraph workflows with structured, reproducible steps
- Have verifiable outputs — the system can confirm success or failure
- Include human approval gates at appropriate decision points
- Are customer-specific and frozen — platform updates never modify them
- Only change when the customer decides (via mechanic proposal → approval)
- Represent accumulated institutional knowledge of how that business operates
- Each SOP has an input schema that can generate a web intake form

### SOP-to-Form Pipeline

When an SOP is created and approved:
1. The SOP definition includes an `inputs:` section listing required fields
2. A web form is generated from this schema (auto or manually)
3. The form is deployed to a client-specific URL
4. Form submissions trigger the LangGraph workflow with structured inputs
5. Travis reviews outputs before delivery (Tier 1) or customer approves inline (Tier 2)

This means every proven workflow automatically becomes a self-service product.

---

## 13. The Mechanics: Self-Improvement Engines

### Two Specialized Mechanics

The original design had one Mechanic. This design splits it into two with distinct responsibilities.

### Mechanic A: Chat Agent Optimization

**Focus:** The conversational layer (OpenClaw).

**Analyzes:** Conversation quality, routing accuracy (did it correctly decide to handle vs. dispatch?), user satisfaction, context management, response quality for simple tasks.

**Proposes:** Changes to OpenClaw's system prompt, routing rules, skill configurations, response templates.

**Inputs:** Slack/Google Chat thread histories, user feedback (emoji reactions), routing decisions and their outcomes.

**Also processes:** OpenClaw's self-modification request notes (when the agent wanted to change its config but couldn't).

### Mechanic B: Workflow Execution Optimization

**Focus:** The execution layer (LangGraph workflows).

**Analyzes:** Every LangGraph run via LangSmith traces. Step-by-step performance, tool usage efficiency, error patterns, cost per step, SOP adherence.

**Proposes:** Workflow optimizations, tool changes, SOP updates, skill additions, pre-installation of proven tools.

**Special capability:** Can re-run a job with proposed optimizations to verify the improvement before proposing it. Only proposes changes that produce equal or better output.

### Mechanic Output Format

Both mechanics produce changes in two formats, shown side by side:

1. **Human-readable summary:** What's changing, why, evidence from the run, expected improvement.
2. **Git diff:** Precise config change against YAML/markdown files. Auditable, revertible.

Posted to the admin channel with Approve/Reject/Edit buttons.

### The Golden Rule

**If either mechanic cannot articulate WHY a change is an improvement with EVIDENCE, it MUST NOT propose the change. Default is always: no change.**

### All Changes Follow the Same Process

1. Mechanic analyzes run
2. Mechanic proposes change (human-readable summary + git diff)
3. Change is posted for review (admin channel or #agent-ops)
4. Travis approves → git commit → config reload / container restart
5. Travis rejects → nothing changes, logged for audit
6. Travis edits → modified change goes through approval again

---

## 14. The Meta-Mechanic

Runs weekly. Reviews both mechanics' performance:
- Are their proposals getting approved or rejected? Why?
- Did approved changes actually improve subsequent runs?
- What patterns are the mechanics missing?
- Should evaluation criteria be updated?

Proposes changes to the mechanics' own system prompts and evaluation criteria. ALL Meta-Mechanic proposals require Travis's approval. This is where the recursive improvement chain terminates with a human.

---

## 15. Secrets Management & Authentication

### Principles

1. Secrets never appear in agent context — injected at runtime, never through the LLM
2. Every secret has a scope — per-workspace, per-project, never cross-tenant
3. Referenced by name, resolved at runtime — agent config says `${secrets.META_ADS_KEY}`
4. All access audited — which secret, which agent, which task, when
5. Easy rotation — one-click or auto-scheduled

### Architecture

**Vault:** Doppler (managed, free tier to start). Per-workspace secret environments. Auto-rotation support. Audit logging built in.

### Secret Categories

| Category | Scope | Rotation |
|----------|-------|----------|
| Platform auth (Slack, Google Chat tokens) | Per workspace | Monthly |
| LLM API keys (Anthropic) | Global | Monthly |
| Tool API keys (Meta Ads, image gen, etc.) | Per workspace | Monthly |
| Git credentials | Per repo | Quarterly |
| Client-specific (CRM, email, SMS APIs) | Per workspace | As client requires |

### Injection Flow

1. Secrets stored in Doppler, organized by workspace
2. KiloClaw instances receive platform secrets as env vars at boot
3. LangGraph tool nodes resolve secrets from environment at call time — LLM never sees them
4. Logs and LangSmith traces are scrubbed of any secret patterns
5. Git pre-push hooks scan for accidentally committed secrets

---

## 16. Security Architecture

### Defense in Depth: Three Rings

**Ring 1: KiloClaw Managed Infrastructure**
Kilo handles VM provisioning, network security, security proxies on Fly.io. Two dedicated proxies per instance manage traffic. Travis has no server to manage.

**Ring 2: Execution Environment Isolation**
Each workspace gets its own KiloClaw instance (separate VM). exec-approvals.json controls commands. Config modification prevented via prompt + allowlist. LangGraph execution containers are disposable.

**Ring 3: Application Permissions**
Command allowlists. Network allowlists per agent role. Per-workspace secrets in vault. Audit logging via LangSmith. Prompt-level restrictions on self-modification.

### Threat Mitigations

| Threat | Mitigation |
|--------|-----------|
| Data exfiltration | KiloClaw security proxies. Secrets never in context. Network allowlists. |
| Secret leakage | Doppler vault. Log scrubbing. Git secret scanning. |
| Runaway execution | Token budgets, time limits, circuit breakers. |
| Cross-tenant data leak | Separate KiloClaw instances. Per-workspace secrets. Slack workspace isolation. |
| Unauthorized deployment | All deploys require explicit human approval. |
| Agent self-modification | Prompt prevention + exec-approvals.json. Mechanic request pattern for desired changes. |
| Platform update breaks customer | Two-layer update model. Customer SOPs frozen. New features OFF by default. |

---

## 17. Observability, Circuit Breakers & Cost Control

### Token & Time Limits
- Per-task token budget (default 100k). Exceeded = terminated, partial results reported.
- Per-task time limit (default 30 min). Exceeded = paused, human notified.

### Circuit Breakers

| Breaker | Trigger | Action |
|---------|---------|--------|
| Token rate | 3x average in first 25% | Pause, alert |
| Error rate | Same error 3x in a row | Pause, ask human |
| Cost (daily) | Daily limit exceeded | Queue new tasks, alert |
| Deploy rate | N+ deploys per day | Require manual confirmation |

### Health Indicators
- Bot status: idle / working / waiting / error
- Context usage percentage per invocation
- `/status` command: tasks, approvals, cost, last mechanic result
- Alerts in admin channel for circuit breakers, errors, security blocks

### LangSmith Traces
Every run produces structured traces: time per node, tokens per call, tool success/failure, cost per run. Mechanics query these for analysis. Travis can browse for debugging.

---

## 18. Quality Gates, Metrics & Acceptance Criteria

### Tracked Metrics
- Tasks completed per day/week (by workspace and overall)
- First-attempt approval rate
- Average revision cycles
- Time from request to approved output
- Token cost per task
- Mechanic improvement rate and approval rate
- Conversation friction score
- SOP coverage (% of tasks matched to SOPs vs. ad-hoc)

### Acceptance Criteria (All Must Pass)

1. Post task in Slack → agent shows plan preview → waits for approval → executes → delivers in-thread
2. Same flow works in Google Chat
3. Reply "no" to preview → agent asks what to change → revises → re-presents
4. After task, Mechanic B posts reflection with scores and proposals
5. Approve mechanic proposal → git shows diff committed → next run uses improved config
6. Reject proposal → config unchanged → git shows no commit
7. Kill system mid-task → restart → graph resumes from checkpoint with full context
8. Run second task in same thread 24 hours later → all prior context present
9. Attempt automatic config change without approval → system blocks it
10. Git revert last change → next run uses previous config
11. Workspace A cannot access Workspace B's secrets
12. Web form submission triggers LangGraph workflow correctly
13. Heartbeat fires on schedule, agent checks in and reports status
14. Agent blocked → actionable DM with options and buttons
15. Morning briefing triggers on presence detection or /checkin
16. All LLM calls use Claude (verify via LangSmith)

---

## 19. Go-to-Market Strategy

### Phase 1: Concierge MVP (Now — Already Active)

Travis drives AI tools manually to produce results. First customer is active and paying $3,000/month, having validated both the outcome and price point. Customer immediately requested continued engagement.

- Operate manually while learning which workflows to automate first
- Every manual engagement teaches which SOPs to build
- Target: 3–5 customers concierge-style for 90 days
- Goal: proof points, workflow patterns, willingness to pay

### Phase 2: Semi-Automated (Near-Term)

- Encode the most common manual workflows as LangGraph SOPs
- Focus on the 20% of workflows that account for 80% of work
- Onboard Tier 2 customers with Slack app
- Launch web intake forms for Tier 1 customers
- Travis still manages but handles less manual execution

### Phase 3: Platform Scale (Future)

- Full mechanic automation
- Self-service Slack app installation
- Rich SOP template library across customer base
- Self-serve Tier 1 with automated delivery
- Tier 2 customers partially self-administering

### Sales Motion

"Add this Slack app and give it a task. See what happens." Or: "Fill out this form. We'll deliver your campaign by Friday."

No slide decks, no free trials with credit cards, no implementation projects. The demo IS the product.

Initial target: marketing teams at 20–50 person companies.

---

## 20. Build Order & Implementation Phases

> **DO NOT SKIP OR REORDER.** Each phase produces a usable system. Ship each before starting the next.

### Phase 0: Validate with Real Work (Week 1)

**Already partially complete — Travis has a paying concierge customer.**

1. Sign up for KiloClaw. Deploy OpenClaw instance. Connect to Slack.
2. Give the bot a real marketing task from the active client
3. Work with it for several days. Document what works and what doesn't.
4. Identify the first 2-3 workflows that should become SOPs
5. Test cron scheduling (daily check-in)
6. Validate: is Slack the right decision layer?

**Deliverable:** Firsthand experience. Clear list of what to automate first.

### Phase 1: LangGraph Integration (Week 2-3)

1. Set up LangGraph Cloud + LangSmith
2. Build first LangGraph workflow from the most common manual task
3. Wire KiloClaw/OpenClaw to dispatch to LangGraph
4. Implement interrupt/resume for approval gates
5. Test: multi-step task with 2+ approval gates
6. Set up git repo for all configuration

**Deliverable:** Working two-layer system. OpenClaw for chat, LangGraph for workflows.

### Phase 2: Security & Secrets (Week 3-4)

1. Set up Doppler for secrets management
2. Migrate all API keys to vault
3. Implement secret injection flow
4. Set up git pre-push secret scanning
5. Configure exec-approvals.json
6. Implement audit logging

**Deliverable:** Production-grade security. Secrets managed properly.

### Phase 3: First SOP + Web Form (Week 4-5)

1. Encode the first proven workflow as a formal SOP (YAML)
2. Build the SOP-to-LangGraph-workflow pipeline
3. Build web intake form from SOP input schema
4. Deploy form to a URL
5. Test: form submission → workflow execution → output delivery
6. Create second and third SOPs from other proven workflows

**Deliverable:** Tier 1 product working. Web form → AI execution → deliverables.

### Phase 4: Mechanics (Week 5-6)

1. Implement Mechanic A (chat agent optimization) as an OpenClaw skill
2. Implement Mechanic B (workflow optimization) as final LangGraph node
3. Write both mechanic system prompts (most important prompts in the system)
4. Implement git diff output format
5. Wire proposals to admin channel with approval buttons
6. Test: run task, verify mechanic reviews, approve change, verify improvement

**Deliverable:** Self-improving system. Every task analyzed.

### Phase 5: Proactive Behavior (Week 6-7)

1. Implement heartbeat cron per project channel
2. Implement block surfacing with actionable notifications
3. Implement morning briefing
4. Implement project completion tracking
5. Implement multi-project prioritization

**Deliverable:** Proactive agent. Customers open Slack to unblock, not to assign.

### Phase 6: Multi-Tenant & Scale (Week 7-9)

1. Set up second workspace for new customer
2. Implement per-workspace secret scoping
3. Test cross-workspace isolation
4. Implement two-layer update model (platform shared vs. customer frozen)
5. Implement Google Chat support for the client that needs it
6. Implement Meta-Mechanic as weekly cron
7. Run all 16 acceptance criteria
8. Security audit

**Deliverable:** Production system serving multiple customers.

### Phase 7: Growth (Week 9+)

1. Onboard customers 3-5
2. Build SOP template library from proven workflows
3. Create customer onboarding automation
4. Begin scaling sales motion
5. Build operational dashboard for Travis

---

## 21. Repository & Configuration Structure

### Platform Config Repo

```
platform/
├── base-config.yaml              # Universal agent config
├── skills/                       # Shared skills (available to all workspaces)
├── tools.yaml                    # Tool definitions and configurations
├── mechanics/
│   ├── mechanic-a-prompt.md      # Chat agent mechanic prompt
│   ├── mechanic-b-prompt.md      # Workflow mechanic prompt
│   ├── meta-mechanic-prompt.md   # Meta-mechanic prompt
│   └── evaluation-criteria.yaml  # Current eval rules
├── docker/                       # Container definitions (for future self-hosting)
└── audit/
    └── metrics.json              # Platform-wide metrics
```

### Per-Workspace Config

```
workspaces/{client-name}/
├── config.yaml                   # Workspace-specific settings
├── context.md                    # Brand guidelines, preferences, notes
├── sops/
│   ├── ad-campaign.yaml          # SOP with input schema
│   ├── landing-page.yaml
│   └── ...
├── skills/                       # Workspace-specific skills
├── forms/                        # Web form configurations
└── improvement-log.md            # Mechanic decision history
```

### LangGraph Code Repo

```
orchestrator/
├── graphs/
│   ├── main.py                   # Main task graph
│   ├── mechanic_b.py             # Workflow mechanic graph
│   └── sop_runner.py             # SOP-driven graph generator
├── nodes/                        # Individual step implementations
├── tools/                        # Tool implementations
├── langgraph.json                # LangGraph Cloud config
└── requirements.txt
```

---

## 22. Key Design Decisions & Rationale

### Workforce, not tool
Customers buy outcomes. The technology is invisible. This commands premium pricing and creates genuine lock-in through accumulated institutional knowledge.

### Two service tiers (web forms + direct access)
Web forms are the lowest-friction entry point. Any business understands "fill out form, get results." Direct Slack access is the premium experience for engaged customers. Same underlying system serves both.

### KiloClaw first, self-host later
Building infrastructure is not where Travis adds value. Building agent intelligence is. $9/month per instance eliminates all ops burden. Self-host only when a documented limitation requires it.

### Two mechanics, not one
Chat optimization and workflow optimization require different analysis skills. Mechanic A watches conversations. Mechanic B watches execution traces. Splitting them produces better, more focused improvements.

### SOPs emerge from use, not upfront design
Writing processes before doing them produces bad processes. The system learns by doing, then codifies what worked. Customer participates in SOP creation through conversation.

### SOP-to-form pipeline
Every proven workflow automatically becomes a self-service product. The SOP defines inputs. The form collects them. The workflow executes. This is how the platform scales beyond Travis's personal bandwidth.

### Two-layer updates (platform shared vs. customer frozen)
Platform improvements benefit everyone. Customer workflows are sacred. New features deploy OFF by default. This prevents the most common SaaS failure: "the update broke our workflow."

### Multi-tenant skill flywheel
Skills built for one client benefit all clients. Development costs are amortized. The platform gets better faster than any single-tenant competitor.

### Git as source of truth
Every change is a commit. Every approval is a merge. Every mistake is a revert. Full audit trail. No ambiguity about what changed, when, why, and who approved it.

### Concierge first, automate later
Travis already has a paying customer. Manual execution while learning which workflows to automate is lower risk than building the full platform before validating demand. Every manual engagement teaches which SOPs to build.

---

## 23. Multi-Agent Swarm: Specialized Agents Per Step

### The Core Principle

LangGraph workflows don't care which agent executes each step. A node needs an input and produces an output. Whether that step is handled by OpenClaw, Perplexity, a computer-use agent, Claude Code, or a specialized API doesn't matter to the graph. This means each step in an SOP can be routed to the best available agent for that specific type of work.

### The Swarm Architecture

OpenClaw is the conversational generalist — it handles chat, routing, simple tasks, and coordination. But within a LangGraph workflow, individual steps can dispatch to specialized agents:

**OpenClaw** — Conversational tasks, simple research, brainstorming, project management, chat coordination. The default for anything that doesn't need a specialist.

**Perplexity** — Deep research with citations and source verification. When an SOP step needs competitive analysis, market research, or fact-checked information, dispatch to Perplexity. It brings significantly higher research quality than generic web search. Perplexity can sit in the Slack workspace as a separate bot and be tagged by OpenClaw when deep research is needed.

**Computer-use agents (Manus, Claude computer use, etc.)** — GUI interaction for platforms that don't have APIs or where the API is incomplete. Configuring Meta Ads Manager, navigating complex dashboards, filling web forms, interacting with tools that require visual interaction. When an SOP step needs to operate a GUI, dispatch to a computer-use agent.

**Claude Code (via acpx)** — Software engineering tasks. Writing code, debugging, refactoring, deploying. When an SOP step involves code generation or modification, dispatch to Claude Code running headlessly in a sandboxed container.

**Specialized API tools** — Direct API calls for structured operations: image generation (DALL-E, Flux, Midjourney), video generation, email sending (Klaviyo, Mailchimp), ad deployment (Meta Ads API), CRM updates (HubSpot, Salesforce), landing page deployment (Vercel, Webflow).

### How It Works in Practice

Each SOP step has an `agent` field that specifies which agent handles it:

```yaml
steps:
  - id: research
    agent: perplexity          # Deep research with citations
    description: Research target audience and competitor positioning

  - id: ideation
    agent: openclaw             # Creative brainstorming
    description: Generate 3-5 campaign concepts

  - id: concept_approval
    type: human_approval        # Pause for human decision

  - id: image_generation
    agent: api:flux             # Direct API call to image gen
    description: Generate product images with campaign styling

  - id: copy_writing
    agent: openclaw             # Generalist handles copy
    description: Write ad copy variants

  - id: landing_page
    agent: claude_code          # Code generation in sandbox
    description: Build and deploy landing page

  - id: meta_ads_config
    agent: computer_use         # GUI interaction for Meta Ads
    description: Configure ad targeting in Meta Ads Manager

  - id: deployment_approval
    type: human_approval        # Final human gate
```

LangGraph routes each step to the appropriate agent. Results flow back into graph state. The human only sees the outputs at approval gates — the agent routing is invisible.

### Adding New Agent Types

Adding a new agent type to the swarm is a configuration change, not an architecture change:

1. Implement a new LangGraph node that calls the new agent
2. Register it in `tools.yaml` with its capabilities and access patterns
3. Reference it in SOP step definitions with `agent: new_agent_name`
4. The Mechanic can discover that a step would benefit from a specialized agent and propose the change

### When to Add Agents (Pragmatic Rule)

**Don't add agents speculatively.** Start with OpenClaw doing everything. When a specific step in a specific SOP is measurably underperforming — research quality is too low, a GUI needs to be operated, code needs to be written — that's when you add the specialized agent for that step.

Each addition is driven by a real limitation, not speculative capability expansion. The Mechanic can detect these limitations: "The research step in the ad campaign SOP was rated 2/5 by the user three times in a row. Consider routing this step to a deep research agent like Perplexity."

### Multiple Bots in One Workspace

For Tier 2 customers (direct Slack access), multiple bots can coexist in the same workspace:

- **The primary bot (OpenClaw)** — the one the customer talks to. Handles conversation, routes tasks, posts results.
- **Perplexity bot** — sits in the workspace. Gets tagged by OpenClaw when deep research is needed. Posts research results in-thread.
- **Other specialist bots** — as needed per workspace. Each brings unique capabilities.

The customer sees multiple bots collaborating in their thread, which actually reinforces the "workforce" positioning — it looks like a team of specialists working together.

### Security Considerations for Multi-Agent

- Each agent type has its own permission scope. Computer-use agents get restricted network access. Research agents get read-only access.
- Secrets are scoped per agent type — a research agent doesn't need deployment credentials.
- All agent interactions are logged in LangSmith traces for the Mechanic to analyze.
- The Mechanic evaluates whether each agent type is performing well for its assigned steps and can recommend re-routing.

---

## Future Vision

### Slack Huddle Participation
Agent joins voice calls, listens via Whisper STT, interjects when asked. Transcript auto-added to thread context. OpenClaw already has voice capabilities.

### Local Hardware Nodes
Mac Mini running OpenClaw connected to physical hardware (USB debuggers, logic analyzers, embedded boards) via Tailscale tunnel. LangGraph dispatches hardware tasks to local node. Premium feature for engineering teams. Not in initial build.

### Self-Service Platform
Customers install the Slack app themselves. Self-serve Tier 1 with automated delivery. Rich SOP template marketplace. The endgame is a platform, not a consulting practice.

---

> **END OF SPECIFICATION**
>
> This document contains everything needed to build the Digital Workforce Platform.
> Build in the order specified in Section 20. Do not skip phases.
> Security and secrets are not optional. The mechanics are the core differentiator.
> SOPs emerge from use — don't write them all upfront.
> The concierge model is already validated with a paying customer.
> If anything is ambiguous, ask Travis.
>
> Build something exceptional.
