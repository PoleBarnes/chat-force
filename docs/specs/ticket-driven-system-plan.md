# Ticket-Driven Agent System — Implementation Plan

**Status:** Ready for implementation
**Instruction to implementer:** Act as orchestrator and delegate work to a team of specialized agents.

---

## Overview

Build a ticket-driven self-improving system on top of the chat-force CLI. The ticket is the contract. The CLI orchestrates three phases per ticket: execution swarm → PM verification → mechanic reflection. Ticket templates define reusable work patterns. The harness compounds over time.

## Source Documents

- `docs/specs/local-cli-chat-force.md` — the local CLI spec (already built)
- `Ticket_Driven_Agent_System_Requirements.docx` — full requirements (35 REQs, integrated into project memory)
- `https://github.com/PoleBarnes/harness-core` — existing tracker abstraction, MCP patterns, field mappings

## Current State

Already built and working:
- `bin/chat-force` shell script (prototype → mechanic handoff)
- `chat-force init` scaffolding with templates
- `templates/general/` with CLAUDE.md, rules, vault structure
- `templates/mechanic-prompt.md` mechanic persona
- Dogfooded: prototype creates files, mechanic analyzes and proposes improvements

---

## Implementation Tasks (in dependency order)

### Phase 1: Ticket Infrastructure

#### Task 1.1: Ticket Template Schema
**What:** Define the ticket template format that lives in `.claude/ticket-templates/`.
**Deliverables:**
- Schema definition (YAML-based) with required fields:
  - `name`: template identifier
  - `description`: what this template is for
  - `required_inputs`: fields the user must provide (with types)
  - `required_artifacts`: files/deliverables that must be produced
  - `acceptance_criteria`: list of verifiable criteria for PM
  - `skills`: list of skill references relevant to this ticket type
- Validation script (`bin/chat-force create-ticket`) that:
  - Reads a template
  - Prompts for required inputs (or accepts them as args)
  - Validates all fields are filled and correctly typed
  - Fails with specific error if any field is missing
- 3 starter templates:
  - `general.yaml` — free-form ticket with basic criteria
  - `research-spike.yaml` — research task, output is vault entries + summary
  - `deliverable.yaml` — produce a specific artifact (landing page, ad copy, etc.)
- Tests: template validation pass/fail, missing fields, type checking

#### Task 1.2: Tracker Abstraction (Rules-Based)
**What:** A `.claude/rules/ticket-operations.md` file that teaches Claude Code CLI how to work with tickets across platforms.
**Deliverables:**
- Normalized field mapping rules (title, description, acceptance_criteria, status, priority, assignee, labels, branch, history)
- Platform-specific translation notes (Linear vs Jira)
- Operations: fetch ticket, create ticket, add comment, add attachment, change state, assign, link branch
- Label-driven state machine: `created → in_progress → pm_review → done` (via labels, not platform states)
- Reference material adapted from harness-core's `tracker-operations.md` and `tracker-linear.md`

#### Task 1.3: Linear MCP Integration
**What:** Configure the Linear MCP server so Claude Code CLI can read/write tickets natively.
**Deliverables:**
- MCP server config for `.claude/settings.json`:
  ```json
  {
    "mcpServers": {
      "linear": {
        "command": "npx",
        "args": ["-y", "@linear/mcp-server"],
        "env": { "LINEAR_API_KEY": "..." }
      }
    }
  }
  ```
- Test: `chat-force` can pull a ticket from Linear, read its fields, add a comment
- Documentation in rules file for how to use the Linear MCP tools

#### Task 1.4: Branch Management
**What:** Automatic branch creation/checkout per ticket.
**Deliverables:**
- Update `bin/chat-force` `run` command:
  - On start: checkout `ticket/<TICKET-ID>` (create from main if doesn't exist)
  - Push commits to the branch during execution
  - Support `--branch <name>` override
- Branch naming convention: `ticket/PROJ-42` (derived from ticket ID)
- If branch exists, checkout and resume from tip

---

### Phase 2: Three-Phase CLI Flow

#### Task 2.1: Update `chat-force run` Command
**What:** Replace `prototype` command with `run <ticket-id>` that executes all three phases.
**Deliverables:**
- New command: `chat-force run <ticket-id> [--branch name]`
  1. Pull ticket from Linear (via MCP)
  2. Checkout/create branch `ticket/<id>`
  3. Launch **execution swarm** (Claude Code CLI session)
     - System prompt includes: ticket description, acceptance criteria, relevant skills
     - ROLE.md orchestrator instructions
     - Swarm knows the acceptance criteria and self-corrects before handing off
  4. On swarm exit: upload attempt summary to ticket history (comment)
  5. Launch **PM verification** (Claude Code CLI session)
     - System prompt: PM persona (verify only, don't fix)
     - Reads ticket acceptance criteria + produced artifacts
     - Outputs pass/fail per criterion
  6. If PASS: present to human for approval → upload artifacts to ticket → change state
  7. If FAIL: present feedback to human → choose: (a) loop again, (b) run mechanic, (c) stop
  8. Launch **mechanic** (Claude Code CLI session)
     - Reads all attempt history from ticket
     - Proposes harness improvements interactively
     - Approved changes committed to branch
- Keep `chat-force prototype` as an alias for free-form work without a ticket

#### Task 2.2: PM Agent Persona
**What:** Create the PM verification persona.
**Deliverables:**
- `templates/pm-prompt.md` — PM system prompt:
  - Role: independent verifier. You only see output, not process.
  - Read the ticket's acceptance criteria
  - Inspect the produced artifacts in the repo
  - For each criterion: pass or fail with specific evidence
  - Present results to human for final approval
  - On approval: upload artifacts to ticket, change state
  - On failure: present failure feedback, return to human for decision
- PM runs with full Read/Grep/Glob access but is instructed to focus on artifacts, not session history

#### Task 2.3: Ticket History
**What:** Every execution attempt leaves a trace on the ticket.
**Deliverables:**
- After each swarm phase: add comment to ticket via MCP with:
  - Attempt number
  - What was tried (brief summary)
  - What was produced (file list)
  - What succeeded / what failed
  - Branch + commit hash
- After PM phase: add comment with:
  - Pass/fail per criterion
  - If fail: specific feedback
- After mechanic phase: add comment with:
  - Harness improvements installed
  - Skills/rules/templates changed
- All comments follow a consistent format (markdown) for machine readability

---

### Phase 3: Ticket Templates and Creation

#### Task 3.1: Template-Based Ticket Creation
**What:** CLI command to create tickets from templates with validation.
**Deliverables:**
- `chat-force create-ticket --template <name> [--field key=value ...]`
  - Reads template from `.claude/ticket-templates/<name>.yaml`
  - If fields not provided as args, launches Claude Code CLI to interview the user
  - Validates all required fields
  - Creates ticket in Linear via MCP
  - Returns the ticket ID
- `chat-force list-templates` — lists available templates with descriptions

#### Task 3.2: Bootstrap Ticket
**What:** A special template for initializing new projects.
**Deliverables:**
- `.claude/ticket-templates/bootstrap.yaml`:
  - Input: project description, goals, constraints
  - Output: a project plan as a set of tickets
  - Acceptance criteria: all generated tickets have acceptance criteria, proper types, and sequencing
- `chat-force init` updated to optionally create a bootstrap ticket after scaffolding

#### Task 3.3: Template Evolution via Mechanic
**What:** The mechanic can propose new templates or improvements to existing ones.
**Deliverables:**
- Update mechanic prompt to analyze: "Are there patterns across recent tickets that suggest a new template?"
- Mechanic can propose new `.claude/ticket-templates/<name>.yaml` files
- Mechanic can propose modifications to existing templates (new required fields, better criteria)
- All proposals go through the same interactive approval flow

---

### Phase 4: Polish and Integration

#### Task 4.1: Jira MCP Integration
**What:** Add Jira support alongside Linear.
**Deliverables:**
- MCP server config for Jira Cloud
- Update `.claude/rules/ticket-operations.md` with Jira field mappings
- Test: same ticket template creates valid tickets in both Linear and Jira
- Platform selection via `.claude/settings.json` config field

#### Task 4.2: `chat-force status`
**What:** Show the current state of work.
**Deliverables:**
- `chat-force status` shows:
  - Current branch and associated ticket
  - Ticket state (from Linear/Jira)
  - Number of execution attempts
  - PM verification status
  - Last mechanic run
- Quick view for "where am I and what's next?"

#### Task 4.3: Documentation and Onboarding
**What:** README, getting started guide, video walkthrough script.
**Deliverables:**
- `README.md` for chat-force: what it is, how to install, quickstart
- `docs/getting-started.md`: step-by-step first project setup
- `docs/ticket-templates.md`: how to create and customize templates
- `docs/for-developers.md`: how a developer uses the system day-to-day

---

## Repo Structure After Implementation

```
chat-force/
├── bin/
│   └── chat-force                      # Main CLI script
├── templates/
│   ├── general/                        # Project scaffold template
│   │   ├── CLAUDE.md
│   │   ├── .claude/
│   │   │   ├── settings.json
│   │   │   ├── rules/
│   │   │   │   ├── brand-voice.md
│   │   │   │   ├── never-list.md
│   │   │   │   ├── eval-criteria.md
│   │   │   │   └── ticket-operations.md
│   │   │   └── ticket-templates/
│   │   │       ├── general.yaml
│   │   │       ├── research-spike.yaml
│   │   │       └── deliverable.yaml
│   │   └── vault/
│   ├── mechanic-prompt.md              # Mechanic persona
│   └── pm-prompt.md                    # PM persona
├── docs/
│   └── specs/
│       ├── local-cli-chat-force.md
│       └── ticket-driven-system-plan.md
└── ...existing engine code (Slack path, preserved)
```

## Customer Project Structure After Init

```
customer-project/
├── CLAUDE.md
├── vault/
├── .claude/
│   ├── settings.json                   # MCP server config (Linear/Jira)
│   ├── rules/
│   │   ├── ticket-operations.md        # Tracker abstraction
│   │   ├── never-list.md
│   │   └── eval-criteria.md
│   ├── skills/                         # Grown by mechanic
│   ├── agents/                         # Grown by mechanic
│   └── ticket-templates/               # Ticket templates
│       ├── general.yaml
│       └── (more grown by mechanic)
├── .mechanic/
│   └── log/
└── src/
```

---

## Success Criteria

1. `chat-force init` scaffolds a project with ticket templates and Linear MCP config
2. `chat-force create-ticket --template research-spike` creates a validated ticket in Linear
3. `chat-force run PROJ-42` pulls the ticket, checks out branch, runs swarm → PM → mechanic
4. PM verification catches missing acceptance criteria and presents failure to human
5. Human approves PM pass → artifacts uploaded to ticket → state changed
6. Mechanic proposes a new skill based on session patterns → human approves → skill installed
7. Next `chat-force run` benefits from the installed skill
8. Ticket history shows all attempts, PM results, and mechanic improvements
9. The same flow works with Jira (Task 4.1) by changing the MCP config

---

## Implementation Notes

- **Delegate aggressively.** Each task above should be delegated to a focused sub-agent. The orchestrator plans and synthesizes; sub-agents write code, templates, and tests.
- **Dogfood each task.** After each task lands, run it against a real Linear ticket before moving to the next.
- **The CLI is a thin shell wrapper.** It launches Claude Code CLI sessions with the right prompts, args, and MCP config. It does NOT contain business logic — Claude Code CLI does the work.
- **Preserve the Slack path.** The existing pipeline/ code (listener, worker, mechanic_manager, credential proxy) stays intact. The local CLI is a parallel interface to the same harness concept.
