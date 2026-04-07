# chat-force CLI — Local Self-Improving Prototyping Tool

**Status:** Spec
**Priority:** Immediate — this is the primary interface
**Replaces:** Slack-first workflow for solo operator and developer use cases

---

## 1. What It Is

A shell script (`chat-force`) that chains two Claude Code CLI sessions:

1. **Prototype session** — full-power Claude Code CLI for building deliverables
2. **Mechanic session** — analyzes the prototype session, proposes harness improvements, installs approved changes interactively

The developer runs `chat-force` in a project repo. They prototype. They stop. The mechanic appears immediately in the same terminal. They approve or reject proposals. The harness improves. Next session benefits.

## 2. Commands

```bash
chat-force init            # Scaffold a new project (.claude/, vault/, .mechanic/, CLAUDE.md)
chat-force prototype       # Run a prototyping session → mechanic handoff
chat-force mechanic <id>   # Run mechanic review on a specific session (manual)
chat-force projects        # List known projects with last session info
```

## 3. Project Structure

```
customer-project/
├── CLAUDE.md                    ← identity, project instructions
├── vault/                       ← project knowledge base (first-class)
│   ├── VAULT.md                 ← schema: how the bot maintains this
│   ├── index.md                 ← catalog of everything
│   ├── log.md                   ← append-only activity log
│   ├── raw/                     ← source materials
│   ├── summaries/               ← per-source and per-session summaries
│   ├── entities/                ← competitors, products, personas
│   ├── concepts/                ← brand voice, market insights
│   └── decisions/               ← decision log
├── .claude/
│   ├── settings.json            ← profiles, hooks
│   ├── rules/                   ← brand voice, never-list, eval criteria
│   │   ├── brand-voice.md
│   │   ├── never-list.md
│   │   └── eval-criteria.md
│   ├── skills/                  ← grown by mechanic over time (starts empty)
│   └── agents/                  ← grown by mechanic over time (starts empty)
├── .mechanic/
│   └── log/                     ← fix proposals, session analyses
└── src/                         ← the actual project code
```

## 4. Prototype Session

```bash
chat-force prototype [-- <extra claude args>]
```

Runs:
```bash
SESSION_ID=$(claude --profile prototype "$@" --output-session-id)
```

The prototype profile:
- System prompt: ROLE.md content (orchestrator + prototyper instructions)
- Full tool access (so sub-agents can inherit all tools)
- Strong delegation instructions: "create sub-agents for execution, you plan and synthesize"
- Reads: CLAUDE.md, .claude/rules/*, .claude/skills/*, .claude/agents/*
- Reads/writes: vault/ (knowledge base)
- No predefined sub-agents — creates them dynamically as needed

## 5. Mechanic Session

When the prototype session exits, the wrapper immediately launches:

```bash
claude --profile mechanic --task "Analyze session $SESSION_ID and propose harness improvements"
```

The mechanic profile:
- System prompt: SOUL.md + IDENTITY.md + AGENTS.md content (mechanic persona)
- Reads the session transcript from ~/.claude/projects/<hash>/
- Reads the git diff from the prototype session
- Reads current .claude/rules/, .claude/skills/, .claude/agents/
- Reads eval criteria from .claude/rules/eval-criteria.md
- Proposes improvements interactively:
  - New skills → .claude/skills/<name>/SKILL.md
  - New rules → .claude/rules/<name>.md
  - New agent definitions → .claude/agents/<name>.md
  - Updated CLAUDE.md
  - Eval criteria changes
  - Vault updates
- Developer approves/rejects each proposal in the terminal
- Approved changes committed with descriptive message
- Proposals (approved and rejected) logged to .mechanic/log/

## 6. chat-force init

Scaffolds a new project:

```bash
chat-force init [--template marketing|firmware|general]
```

Creates:
- `CLAUDE.md` from template (identity placeholders)
- `vault/` with VAULT.md schema + empty structure
- `.claude/settings.json` with prototype + mechanic profiles
- `.claude/rules/` with starter rules (never-list, eval-criteria)
- `.mechanic/log/` empty directory
- `.gitignore` additions (if needed)

Templates:
- `general` (default) — minimal, no domain assumptions
- `marketing` — brand voice rules, campaign-oriented eval criteria
- `firmware` — hardware interaction rules, safety-first eval criteria

## 7. Session Artifact Flow

```
Prototype session (Claude Code CLI)
    ↓ writes to
~/.claude/projects/<hash>/         ← session transcript (auto by Claude Code)
vault/summaries/sessions/<date>.md ← session summary (written by prototype)
git diff                           ← file changes in the repo

    ↓ read by

Mechanic session (Claude Code CLI)
    ↓ writes to
.claude/skills/                    ← new skills (approved by developer)
.claude/rules/                     ← new rules (approved)
.claude/agents/                    ← new agent definitions (approved)
.mechanic/log/<date>-<slug>.md     ← proposal record (all proposals)
```

## 8. What We Keep From the Engine Work

| Component | Reuse | Where |
|---|---|---|
| ROLE.md | Prototype profile system prompt | Template for CLAUDE.md or .claude/rules/ |
| SOUL.md + IDENTITY.md + AGENTS.md | Mechanic profile system prompt | Bundled with chat-force CLI |
| Harness schema (vault structure) | vault/ template | chat-force init |
| scrub_secrets() | Mechanic scrubs before logging | In the mechanic profile instructions |
| Self-modification deny-list | Mechanic checks for scope creep | In eval criteria template |
| Eval criteria schema | .claude/rules/eval-criteria.md | Template |

## 9. What We Don't Need

- Docker Worker container (CLI runs natively)
- SDK entrypoint.py (Claude Code CLI is the runtime)
- Credential proxy (developer uses their own Claude auth)
- Slack listener (add later for convenience)
- HarnessLoader / workspace.yaml (project structure IS the config)
- SessionManager / SessionStore (Claude Code manages sessions)
- WorkerManager (no containers to manage)

## 10. Implementation Order

1. Write the `chat-force` shell script (prototype → mechanic handoff)
2. Write `chat-force init` (scaffold templates)
3. Create the mechanic profile (SOUL + IDENTITY + AGENTS as a .claude/agents/ definition)
4. Create the prototype profile (ROLE.md as rules)
5. Create the starter templates (general, marketing, firmware)
6. Dogfood on a real project
7. Iterate mechanic quality based on real sessions

## 11. Definition of Done

- `chat-force init` creates a valid project structure
- `chat-force prototype` drops into Claude Code CLI with the right context
- On exit, mechanic launches automatically with the session ID
- Mechanic proposes at least one improvement from a real session
- Developer approves interactively, changes committed
- Next prototype session benefits from the improvement
- The full loop works without Docker, without Slack, without the SDK
