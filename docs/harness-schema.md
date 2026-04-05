# Harness Schema

> **Status:** Draft — requires review before S1.3 implementation begins.
>
> **Audience:** Anyone adding a new customer, anyone modifying the engine's harness-loading code, anyone onboarding a new bot.

---

## 1. What A Harness Is

A **harness** is a per-customer git repository that plugs into the shared `chat-force` factory engine to produce one branded bot for one customer.

Every deployment in production runs:

```
systemd unit → chat-force engine + HARNESS_PATH + Doppler config
            ↓
         one Slack App (one bot) in one workspace
```

The engine is identical for every customer. Everything customer-specific lives in the harness.

### What's in a harness (the mental model)

A harness answers four questions about one bot:

1. **Who is this bot?** — identity, brand, mission, voice, guardrails
2. **What is "good"?** — eval criteria, must-haves, never-list
3. **How does it work?** — skills (grown by the factory over time)
4. **Where does it plug in?** — Slack tokens, channel IDs, git identity, deliverable backend, limits

The first three are *content*. The fourth is *configuration*. Both live in the same repo because they travel together: you never want to redeploy the content without the config, or vice versa.

### What's NOT in a harness

- Engine code (`pipeline/`, `worker/`, `tests/`) — that's the shared factory
- The Mechanic Agent's own persona (`mechanic/config/`) — the "how to review" logic is universal
- Any shared skills or templates — those live in the engine or a template repo (TBD)
- Secrets (API keys, tokens) — those live in Doppler, referenced by env var name in `workspace.yaml`

---

## 2. Canonical Directory Structure

```
harness-<slug>/
│
├── workspace.yaml              # REQUIRED — engine config: bot, git, channels, limits, secrets refs
├── slack-manifest.json         # REQUIRED — Slack App manifest (start from docs/templates/slack-manifest.json)
├── README.md                   # REQUIRED — what this harness is, who owns it
│
├── identity/                   # REQUIRED — who the bot is
│   ├── mission.md              # mission, goals, what this bot exists to do
│   ├── brand.md                # voice, tone, colors, vocabulary
│   ├── avatar.md               # ICP / target audience the bot serves
│   ├── never-list.md           # things the bot must never say or do
│   └── bot-persona.md          # the bot's personality, style, flair
│
├── eval/                       # REQUIRED — what "good" looks like
│   └── criteria.yaml           # narrative + checklist the Mechanic Agent uses
│
├── skills/                     # REQUIRED (empty at start) — factory-grown workflows
│   └── <skill-slug>.md         # each follows the skill file template
│
├── mechanic-log/               # REQUIRED (empty at start) — compounding fix log
│   └── YYYY-MM-DD-<slug>.md    # structured entries, one file per fix
│
├── vault/                      # REQUIRED — per-customer LLM knowledge base
│   │                           # (start from docs/templates/vault-starter/ — Karpathy LLM Wiki pattern)
│   ├── VAULT.md                # the schema: how the LLM maintains this vault
│   ├── index.md                # catalog of every page, grouped by category
│   ├── log.md                  # append-only log of ingests, queries, lints
│   ├── raw/                    # Layer 1 — immutable sources (brand guides, PDFs, etc.)
│   ├── summaries/
│   │   ├── sources/            # one summary per ingested raw source
│   │   └── sessions/           # one summary per factory-floor session
│   ├── entities/               # LLM-generated entity pages (competitors, products, personas, ...)
│   ├── concepts/               # LLM-generated concept pages (brand voice, category insights, ...)
│   └── decisions/              # LLM-generated decision log ("we tried X, result was Y, lesson is Z")
│
├── brand-assets/               # OPTIONAL — extra reference materials outside the vault
│   └── <whatever>.{md,pdf,png,...}
│
└── deliverables-config.yaml    # OPTIONAL — where finished work goes; defaults to filesystem
```

**Start from templates.** Every new harness begins by copying two things from the engine repo:
- `docs/templates/slack-manifest.json` → `harness-<slug>/slack-manifest.json` (then fill in `REPLACE_ME_*` values)
- `docs/templates/vault-starter/` → `harness-<slug>/vault/` (then leave the directories empty for the factory to populate)

### Required vs optional

| Path | Required | Why |
|------|----------|-----|
| `workspace.yaml` | **Required** | Engine cannot start without it |
| `slack-manifest.json` | **Required** | Source of truth for the Slack App config. Pasted into Slack UI to create/update the bot. |
| `README.md` | **Required** | Human context for anyone opening the repo |
| `identity/mission.md` | **Required** | Fed into Worker system prompt |
| `identity/brand.md` | **Required** | Fed into Worker system prompt |
| `identity/avatar.md` | **Required** | Fed into Worker system prompt |
| `identity/never-list.md` | **Required** | Hard boundaries — fed into Worker prompt AND eval |
| `identity/bot-persona.md` | **Required** | Voice / personality, fed into Worker system prompt |
| `eval/criteria.yaml` | **Required** | Mechanic Agent cannot evaluate without it |
| `skills/` (directory) | **Required** | Worker system prompt loads skills from here; grown by factory |
| `mechanic-log/` (directory) | **Required** | Engine writes fix proposals here; cannot write to a nonexistent dir |
| `vault/VAULT.md` | **Required** | The schema the LLM reads to know how to maintain the vault |
| `vault/index.md` | **Required** | Empty-but-present catalog; vault ops refuse to run without it |
| `vault/log.md` | **Required** | Empty-but-present op log |
| `vault/raw/` (directory) | **Required** | Where sources land before ingest |
| `vault/summaries/sources/` | **Required** | Where per-source summaries land |
| `vault/summaries/sessions/` | **Required** | Where per-session summaries land |
| `vault/entities/`, `vault/concepts/`, `vault/decisions/` | **Required** | LLM-written wiki layers |
| `brand-assets/` | Optional | Supplementary reference material outside the vault |
| `deliverables-config.yaml` | Optional | Defaults to filesystem-based delivery |

**Validation rule:** Engine refuses to start if any REQUIRED file or directory is missing. Error message must name the exact missing path.

**The three factory-grown pillars.** Inside every harness, three directories are the compounding assets that grow over time:

| Pillar | Contains | Who writes |
|--------|----------|------------|
| `skills/` | How to do things (codified workflows) | Mechanic Agent proposes; human approves |
| `mechanic-log/` | What broke and how it was fixed | Mechanic Agent writes; human reviews |
| `vault/` | What the bot knows about this customer | Worker ingests/queries; Mechanic lints; human corrects |

All three are isolated per customer. No cross-harness sharing without explicit human action.

---

## 3. `workspace.yaml` Schema

The single most important file in the harness. The engine parses this at startup.

```yaml
# Schema version — engine refuses to start if this doesn't match a known version
schema_version: 1

# Human-readable identifier for this harness
# Used in logs, metrics, directory names. Must match the repo name slug.
slug: "black-tie"

# --- Bot identity in Slack ---
bot:
  display_name: "BlackTie"                # what users see in Slack
  avatar_path: "./assets/avatar.png"      # optional, relative to harness root
  slack_app_id: "A012345"                 # reference, not a secret
  slack_bot_token_env: "BLACK_TIE_SLACK_BOT_TOKEN"   # Doppler var name
  slack_app_token_env: "BLACK_TIE_SLACK_APP_TOKEN"   # Doppler var name (socket mode)

# --- Git identity (used when the Worker makes commits) ---
git:
  user_name: "black-tie-bot"
  user_email: "bot@blacktiecomponents.com"
  # optional — only if this bot pushes to GitHub
  github_token_env: "BLACK_TIE_GITHUB_TOKEN"
  github_username: "black-tie-bot"        # machine user handle, not a secret

# --- Slack channel topology ---
# Each channel has a defined role with different engine handling
channels:
  intake: "C01BLKINTAKE"           # public, customer-facing, gated by eval
  factory_floor: "C01BLKFLOOR"     # private, prototyper + bot
  mechanic_log: "C01BLKMECHLOG"    # private, structured fix log
  brand_assets: "C01BLKASSETS"     # private, knowledge base (read-only for bot)

# --- Access control ---
access:
  # Slack user IDs allowed to trigger this bot. If empty, NOBODY can trigger it.
  allowed_user_ids:
    - "U0AG4Q4G1FB"   # Travis
    # - "U0ANNAXXXXX"  # Anna (future)

# --- Runtime limits ---
limits:
  max_concurrent_sessions: 1              # this bot can only run N sessions at once
  max_budget_usd_per_session: 5.0         # hard cap per session
  max_budget_usd_per_day: 30.0            # hard cap per rolling 24h
  max_turns_per_session: 50               # agent SDK max_turns
  session_idle_timeout_seconds: 600       # close session after N seconds idle
  worker_timeout_seconds: 600             # kill worker after N seconds on a single turn
  mechanic_timeout_seconds: 300           # kill mechanic after N seconds

# --- Deliverable backend (where outputs land) ---
deliverables:
  backend: "filesystem"                   # options: filesystem | google_drive | obsidian (future)
  # backend-specific config follows
  filesystem:
    path: "/var/lib/chat-force/deliverables/black-tie"
```

### Validation rules for `workspace.yaml`

1. `schema_version` must be a known integer (currently only `1` is valid)
2. `slug` must match `^[a-z0-9-]+$` and be ≤ 32 chars
3. `bot.display_name` must be non-empty
4. `bot.slack_bot_token_env` and `bot.slack_app_token_env` — the engine checks these env vars EXIST at startup; if missing, refuses to start
5. `git.user_name` and `git.user_email` must be non-empty
6. `channels.*` — all four channel IDs must look like Slack channel IDs (`C...`)
7. `access.allowed_user_ids` must be a non-empty list (empty list = denied-all, but must be explicit)
8. `limits.*` — all must be positive numbers
9. `deliverables.backend` must be one of the supported values; backend-specific config must be present if required

Engine produces one clear error per invalid field and exits non-zero. Never partial-loads a broken harness.

---

## 4. `eval/criteria.yaml` Schema

Machine-readable version of the customer's eval checklist. Currently engine just loads this and passes the criteria text into the Mechanic's prompt. Future: the engine runs mechanical checks (URL validation, spell-check, link-check) before handing off to the Mechanic.

```yaml
schema_version: 1

# Customer's narrative answer to "what does good look like for us?"
# Fed verbatim into Mechanic Agent's evaluation prompt
narrative: |
  We're a premium men's accessories brand targeting affluent professionals.
  Every asset must feel elevated, never salesy. Copy is short, confident,
  never uses exclamation marks or emojis. Visuals lean monochrome.

# The mechanical checklist. Each item is a hard gate — all must pass.
checks:
  - id: on_brand
    description: "Colors, tone, vocabulary match brand guide"
    type: llm_judge                 # llm_judge | regex | url_check | length | custom
  - id: no_exclamation
    description: "No exclamation marks in copy"
    type: regex
    pattern: "!"
    must_not_match: true
  - id: valid_urls
    description: "Every URL resolves to 200"
    type: url_check
  - id: on_target
    description: "Speaks to the defined avatar/ICP in identity/avatar.md"
    type: llm_judge
  - id: no_never_list
    description: "Does not contain anything in identity/never-list.md"
    type: llm_judge
```

For the S1 extraction, `eval/criteria.yaml` can be a minimal placeholder file. The `type: llm_judge` checks don't need implementation yet — they just get passed into the Mechanic prompt as "evaluate against these criteria." Mechanical checks (`regex`, `url_check`) come later.

---

## 5. `mechanic-log/` Schema

Each fix or mistake is a markdown file with YAML frontmatter:

```markdown
---
date: 2026-04-04T15:30:00Z
job_id: session-20260404-153000-abc123
mistake: |
  Ad copy contained an exclamation mark, violating brand rule.
root_cause: |
  Worker was not given the "no exclamation marks" rule in its system prompt.
  It was in brand.md but the relevant section was truncated during context assembly.
fix_type: prompt_update          # skill | eval | prompt_update | tool_config | process
fix_detail: |
  Added explicit "NEVER use exclamation marks in generated copy" to bot-persona.md.
  Added eval check `no_exclamation` to criteria.yaml.
verified: true
verified_at: 2026-04-04T16:05:00Z
severity: medium                 # low | medium | high
---

# Optional: longer freeform notes about the incident
```

Engine writes these files when a mistake is logged. Human (the mechanic, you) reviews, edits, approves. Approval installs the fix by modifying other files in the harness (adding a skill, updating eval criteria, etc).

---

## 6. How The Engine Loads A Harness

### Resolution order

1. `HARNESS_PATH` environment variable (absolute path to harness root)
2. `--harness-path` CLI flag (overrides env)
3. Error if neither is set

### Load sequence at startup

1. Resolve `HARNESS_PATH`
2. Verify path exists and is a directory
3. Load and validate `workspace.yaml` — fail fast on schema errors
4. Verify all required secrets (env vars) exist in the environment
5. Verify all required directories exist (`identity/`, `eval/`, `mechanic-log/`)
6. Verify all required files exist (`identity/*.md`, `eval/criteria.yaml`)
7. Load identity files into memory for system-prompt assembly
8. Load eval criteria into memory for Mechanic Agent
9. Register the bot with Slack using the configured tokens
10. Start the session manager, idle checker, etc.

If **any** step fails, log a clear error naming the exact problem and exit non-zero. Never start in a partially-valid state.

### What the engine passes to the Worker container

The Worker container receives (via bind mount, or via files copied at container start):

- `/harness/identity/*.md` — read-only
- `/harness/skills/*.md` — read-only
- `/harness/brand-assets/**` — read-only
- `/harness/vault/**` — read-write (if present)

Never passes `workspace.yaml` into the container (contains token env var names; the Worker doesn't need them — the Worker gets secrets injected via env by the engine).

Never passes `mechanic-log/` into the container (it's an out-of-band channel — only the engine writes there).

### What the engine passes to the Mechanic Agent (on host)

- `identity/mission.md`, `identity/brand.md`, `identity/avatar.md`, `identity/never-list.md` — context for evaluation
- `eval/criteria.yaml` — the customer's definition of "good"
- The session artifacts (git diff, tool log, usage) from the Worker run
- The engine's own mechanic-persona (from `chat-force/mechanic/config/`) — the "how to review" logic

---

## 7. Failure Modes & Error Messages

| Failure | Error message | Exit behavior |
|---------|---------------|---------------|
| `HARNESS_PATH` not set | `HARNESS_PATH environment variable is required. Set it to an absolute path to a harness repository.` | Exit 1 |
| Path does not exist | `Harness path does not exist: <path>` | Exit 1 |
| `workspace.yaml` missing | `Required file missing: <path>/workspace.yaml` | Exit 1 |
| `workspace.yaml` invalid YAML | `workspace.yaml parse error: <parser message>` | Exit 1 |
| `workspace.yaml` schema mismatch | `workspace.yaml invalid at field "<field>": <reason>. Expected: <expected>. Got: <got>.` | Exit 1 |
| Required secret env var missing | `Required secret env var missing: <name> (referenced by workspace.yaml <path>)` | Exit 1 |
| Required identity file missing | `Required identity file missing: <path>/identity/<name>.md` | Exit 1 |
| `eval/criteria.yaml` missing | `Required file missing: <path>/eval/criteria.yaml` | Exit 1 |

Every error names the exact path and the exact field. No generic "configuration error."

---

## 8. Deployment Model Reminder (So The Schema Makes Sense)

Each deployed customer = one systemd unit:

```
/etc/systemd/system/chat-force@black-tie.service

[Service]
Environment="HARNESS_PATH=/var/lib/chat-force/harnesses/harness-black-tie"
Environment="DOPPLER_PROJECT=chat-force"
Environment="DOPPLER_CONFIG=black-tie"
ExecStart=/usr/local/bin/doppler run -- /opt/chat-force/bin/chat-force-listener
Restart=always
...
```

One engine binary on the host. N systemd units. N harness directories under `/var/lib/chat-force/harnesses/`. N Doppler configs (one per customer, secrets namespaced).

All four customers run as four processes on one host. One workspace (yours), four distinct Slack Apps, four distinct bots — but same workspace, same factory floor infrastructure, fully isolated otherwise.

---

## 9. Open Questions (To Resolve Before Implementation)

The five open questions from the first draft of this document have all been resolved:

1. **Harness location.** Dev: sibling directory (e.g., `/Users/travis/harness-black-tie/`). Prod: `/var/lib/chat-force/harnesses/harness-<slug>/`. Engine reads `HARNESS_PATH` — it doesn't care where on disk the harness lives.

2. **`mechanic-log/` write path.** Engine writes files directly, never commits. Human reviews in the `#<slug>-mechanic-log` Slack channel and commits via PR. Log files are append-only; approved fixes land in `skills/`, `eval/`, or `identity/` via the normal PR flow.

3. **Secrets in Doppler.** Prod: one Doppler project (`chat-force`), one config per customer (`black-tie`, `mailbox-money`, etc.). Dev: prefixed names in a single config are acceptable.

4. **Anthropic API key.** Shared `ANTHROPIC_API_KEY` across all bots for v1. Per-bot keys added later once we need per-customer cost attribution and blast-radius isolation.

5. **Engine writes to the harness repo.** Engine only writes to `mechanic-log/` (log entries, never commits) and `vault/` (session summaries, vault index updates, vault log). Everything else in the harness — skills, eval, identity, workspace.yaml — is human-edited via PR. The Mechanic Agent proposes fixes by writing log entries; a human approves and PRs the actual changes.

---

## 10. Anti-Goals

Things this schema deliberately does NOT include:

- **No `sops/` directory.** SOPs are just complex skills. Rigidity comes from verification, not from a separate abstraction.
- **No per-harness Mechanic persona.** The Mechanic is universal engine logic. Per-customer customization happens through eval criteria, not through different Mechanic personas.
- **No cross-harness linking.** Harnesses are isolated. Any knowledge transfer between customers is an explicit manual operation by the human mechanic, not an engine feature.
- **No shared skills directory.** Every skill lives in exactly one harness. If a skill should be in every harness, it belongs in the engine's starter template, not in a shared location.
- **No engine-defined channel names.** Channel IDs come from `workspace.yaml`. The engine knows about channel *roles* (intake / factory floor / mechanic log / assets), not channel names.
- **No hardcoded deliverable backend.** `deliverables-config.yaml` plus a pluggable adapter. Start with filesystem; add Google Drive, Obsidian, platform-native later as customer needs demand.
