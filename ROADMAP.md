# Roadmap

This is the current execution plan to get chat-force from where it is today to **first customer deployment live**. It is dependency-ordered: each phase unblocks the next.

REQUIREMENTS.md is the stable target. This file is the dynamic sequence. When a phase completes, check off its items in REQUIREMENTS.md Part 1 and update this file's status.

**Not a task tracker.** Live task state is in the agent's task list and in git commits. This file describes the milestones, not the to-do items within them.

---

## Where We Are Now

- Agent SDK pivot complete (engine uses `ClaudeSDKClient` + host-side `query()`)
- 183 fast tests + 10 slow real-service tests passing
- Full pipeline proven end-to-end (real Docker + real Claude + real GitHub PRs)
- Slack listener working in socket mode, dogfooded in Travis's workspace
- Canonical doc set finalized: `CLAUDE.md`, `REQUIREMENTS.md`, `factory-blueprint.md`, `docs/architecture.md`, `docs/harness-schema.md`, templates for Slack manifest + vault starter + grill-me skill
- Mechanic persona extended with customer-feedback ingestion, session analysis, vault lint, and TDD requirements on every proposal

## Where We're Going

One Slack workspace (Travis Hendrickson), one systemd unit per customer bot, one harness repo per customer. First customer live as a real, recoverable, observable, security-hardened deployment. Target: ~4–6 weeks of focused solo-plus-LLM work on the critical path below.

## Critical Path (strict execution order)

Each phase has a clear goal, the REQUIREMENTS.md items it closes, and a definition of done. Phases cannot start until their prerequisite phases are done (unless explicitly called out as parallelizable).

| # | Phase | Goal (one sentence) | Rough size |
|---|-------|---------------------|-----------|
| P0 | **Engine / Harness Split** | Engine loads a harness from `HARNESS_PATH`; zero customer-specific content remains in chat-force. | 4–5 days |
| P1 | **Correctness Fixes on Extracted Architecture** | Multi-turn robust, Mechanic structured output, crash surfacing, timeouts kill containers, limits plumbed from `workspace.yaml`. | 3–4 days |
| P2 | **Persistence & Recovery** | Listener restart is safe: SQLite session store, container reconciliation on boot, approved-verdict durability. | 3–4 days |
| P3 | **Security Hardening (Critical)** | Allowlist, container cap_drop/limits, egress allowlist, secret scanner, path traversal, scrubbed exceptions, self-modification deny-list. | 4–5 days |
| P4 | **Channel Routing + Vibe Loop + Context Visibility + Grill-Me** | Per-channel handlers, eval gate on intake, `grill-me` invoked when harness is thin, context % on every reply, mechanic-log writer. | 4–5 days |
| P5 | **Observability & Supervision** | Structured JSON logs with `run_id`, Prometheus metrics, Sentry, systemd unit, disk cleanup thread. | 2–3 days |
| P6 | **First Customer Harness Population** | One real harness repo populated, Slack App created from manifest, Doppler configured, four channels live. | 2–3 days |
| P7 | **Production Cutover & Smoke** | Systemd deploy, end-to-end smoke in real workspace, first real deliverable shipped, first real mechanic-log proposal reviewed. | 1–2 days |

**Total critical-path work: 23–31 days.**
**Calendar: ~5–6 weeks** at ~5 effective days/week for a solo developer + LLM pair with review cycles.

---

## Phase Details

### P0 — Engine / Harness Split

**Goal.** After this phase, `python -m pipeline.slack_listener` refuses to start without `HARNESS_PATH`, loads all identity/eval/workspace config from the external harness, and contains zero customer-specific strings.

**REQUIREMENTS.md Part 1 items closed:**
- Engine loads a harness from `HARNESS_PATH`
- `HarnessLoader` validates all required files at startup
- Engine contains zero customer-specific content
- `worker/Dockerfile` does not bake customer files into the image
- All harness sections wired end-to-end (`identity/`, `eval/`, `skills/`, `mechanic-log/`, `vault/`)
- `workspace.yaml` schema parsed and applied

**Work items.**
1. Write `pipeline/harness_loader.py` with a `HarnessLoader` class implementing the load sequence from `docs/harness-schema.md` §6. Every failure raises with the exact offending path/field per the §7 error table.
2. Define the `workspace.yaml` schema as a Pydantic model (or validating dataclass).
3. Refactor `pipeline/config.py`, `slack_listener.py`, `worker_manager.py`, `mechanic_manager.py` to read customer-specific values from the loaded harness, not from constants.
4. Rewrite `worker/Dockerfile` to bind-mount identity/skills/vault at container start, not `COPY` them into the image.
5. Update the Mechanic Agent prompt assembly to inject `eval/criteria.yaml` from the loaded harness.
6. Create `tests/fixtures/harness-fixture/` — a minimal-but-valid harness used by the test suite.
7. Delete `skills/` from chat-force root (move starter skills into `docs/templates/skills/` only).
8. Update all existing tests to point at `HARNESS_PATH=tests/fixtures/harness-fixture/`.

**Definition of Done.**
- `grep -ri "leo\|blacktie\|mailbox" pipeline/ worker/ mechanic/` returns nothing (outside fixtures).
- All 183 fast tests pass against the fixture harness.
- Starting without `HARNESS_PATH` → exit 1 with the canonical error.
- Starting with a deliberately broken harness → exit 1 naming the exact bad field.

**Parallelizable with.** Context-window visibility implementation can start in parallel — it only touches `slack_listener.py` response formatting.

---

### P1 — Correctness Fixes on Extracted Architecture

**Goal.** Happy path is durable: multi-turn works, structured verdicts parse, crashes surface within seconds, timeouts actually kill containers, every limit comes from `workspace.yaml`.

**REQUIREMENTS.md items closed:**
- Multi-turn works end-to-end with zero race conditions
- Mechanic Agent uses structured output for verdicts
- Mechanic parse failures surface as distinct error state
- Worker crash → `/tmp/worker-error.txt` → surfaced to user within seconds
- `wait_for_completion` timeout actually kills the container before raising
- `max_budget_usd`, `max_turns`, `IDLE_TIMEOUT` plumbed from `workspace.yaml`
- Global concurrency cap enforced via semaphore
- Every external call has retry with exponential backoff

**Work items.**
1. Mechanic structured output end-to-end — Pydantic verdict model; parse failure raises `MechanicParseError` → distinct `mechanic_error` status → scrubbed message to Slack. No silent rejection storms.
2. Worker crash path — on `/tmp/worker-error.txt` present, transition session to `WORKER_CRASHED` within one poll tick, post scrubbed trace, force-remove container.
3. `wait_for_completion` kill-before-raise — `container.kill()` before `TimeoutError`. Slow-tier integration test with a sleep-forever worker.
4. Limits plumbing — `WorkerManager.start()` reads all limits from the loaded harness. Zero hardcoded defaults in pipeline code.
5. Concurrency semaphore — `limits.max_concurrent_sessions` enforced at session creation; backpressure with max-wait then loud reject.
6. Retry wrapper — `pipeline/retry.py` with exponential backoff + jitter, applied to Slack, Docker, `gh`, Claude SDK calls.

**Definition of Done.** New tests per item, all green. Slow tier re-runs clean.

**Parallelizable with.** Context-visibility track continues.

---

### P2 — Persistence & Recovery

**Goal.** Listener can be killed and restarted with in-flight sessions intact. No container orphans. No lost approved-but-unpushed verdicts.

**REQUIREMENTS.md items closed:**
- Session state survives listener restart (SQLite-backed)
- Approved verdicts persist to disk immediately
- Container reconciliation on listener startup
- Disk cleanup thread runs hourly (minimal version)

**Work items.**
1. SQLite schema + rewrite `SessionManager` to be SQLite-backed; in-memory index is a cache over SQLite.
2. Approved-verdict atomicity — verdict written to SQLite + `runs/<run_id>/verdict.json` before PR creation begins. On restart, resume PR creation for any APPROVED verdict without `pr_url`.
3. Container reconciliation — query `docker ps` for `chat-force.run_id=*` labels at startup, cross-reference with SQLite, force-remove unknowns, reattach known-alive.
4. Add `chat-force.run_id` + `chat-force.harness_slug` labels to every worker container at creation.
5. Disk cleanup — hourly background thread pruning subtrees older than N days from the runs directory.

**Definition of Done.** Kill listener mid-turn → restart → session intact. Kill between approval and PR creation → restart → PR gets created.

**Parallelizable with.** P3 (security) can begin once P2's reconciliation lands — different files.

---

### P3 — Security Hardening (Critical Findings)

**Goal.** Every Critical item from the production review is closed. Safe to expose to a user who is not Travis.

**REQUIREMENTS.md items closed:**
- Slack user allowlist enforced at handler entry
- `GITHUB_TOKEN` never in URLs/logs — credential helper
- Worker container: `cap_drop=ALL`, `no-new-privileges`, resource limits
- Worker restricted egress (allowlist)
- Self-modification deny-list (`.github/`, `worker/`, `pipeline/`, `mechanic/`)
- Changeset extractor uses list-form subprocess; path traversal rejected in `PRCreator._write_file`
- Secret scanner (gitleaks) runs on every changeset; any finding blocks PR
- Exception messages scrubbed before surfacing to Slack

**Work items.**
1. Allowlist enforcement at handler entry — unauthorized users get a single ephemeral "not authorized" reply, zero engine work.
2. Credential helper for git operations (no token in URL, no token in logs).
3. Container hardening — `cap_drop`, `security_opt`, `mem_limit`, `cpu_quota`, `pids_limit` from harness limits.
4. Egress proxy or `iptables`-restricted network — allowlist of `api.anthropic.com`, `github.com`, `api.github.com`, `registry.npmjs.org`, `pypi.org`, `files.pythonhosted.org`. Adversarial test: `curl evil.com` from worker fails.
5. Self-modification deny-list in `changeset_extractor.py` — reject any file path under `.github/`, `worker/`, `pipeline/`, `mechanic/`, `tests/`. Status: `REJECTED_SELF_MODIFICATION`.
6. Path traversal rejection in `PRCreator._write_file` — resolve absolute path, assert under clone root.
7. Subprocess hygiene sweep — kill any remaining `shell=True` or string-interpolated commands.
8. Gitleaks integration — run on the staged diff pre-PR; any finding blocks.
9. Central `scrub_secrets()` function; every Slack error post goes through it; unit-tested with fake tokens.

**Definition of Done.** Adversarial tests pass (worker cannot self-modify engine, cannot exfiltrate via egress, cannot leak tokens through errors).

**Flag for Travis.** The egress proxy is the biggest time sink here. Fallback: run worker with `--network none` and bind-mounted pip/npm cache if full proxy blows the budget. **Decide at P3 start.**

---

### P4 — Channel Routing + Vibe Loop + Context Visibility + Grill-Me

**Goal.** User posts in `#<slug>-intake` → engine creates session → bot works in `#<slug>-floor` → deliverable ships with context percentage footer. Grill-me fires when the harness is thin. Mechanic writes to `#<slug>-mechanic-log`.

**REQUIREMENTS.md items closed:**
- Listener routes by channel role (intake/floor/mechanic-log/assets)
- User posts in `#intake` → session → collaborates in `#floor` → deliverable ships
- Eval mechanical checks run on output before it leaves `#intake` (LLM-judge via Mechanic for v1; regex/url_check deferred to v1.1)
- Bot has read access to harness `vault/`
- Deliverables land in configured backend per `workspace.yaml.deliverables`
- Mechanic Agent writes structured fix proposals to `mechanic-log/`
- Proposals surface in `#<slug>-mechanic-log` channel
- **Grill-me skill invoked whenever harness identity/eval is thin or customer asks for something the harness doesn't support well**
- **Grill-me updates harness files in real time as the customer answers**
- **Every grill session produces a summary in `vault/summaries/sessions/`**
- **Context window usage visible on every bot turn as a percentage with threshold indicators (🟢/🟡/🔴)**

**Work items.**
1. Channel role resolution in `slack_listener.py` — incoming `channel` → `role` from `workspace.yaml.channels`. Unknown channel → ignore.
2. Role handlers — `intake` runs full vibe loop with Mechanic eval gate before replying; `floor` is free prototyping (Mechanic runs after, not before); `mechanic_log` is engine-write-only; `assets` ingests uploads to `vault/raw/uploads/`.
3. Deliverable adapter — `pipeline/deliverables.py` with `FilesystemDeliverable`. Other backends fail loud.
4. Mechanic-log writer — after session, write structured proposal to `harness/mechanic-log/<date>-<slug>.md`; post notification in `#<slug>-mechanic-log`.
5. **Grill-me integration** — before running the vibe loop in `#intake`, check harness thinness (required eval/identity fields populated?). If thin, invoke `skills/grill-me.md` as the system behavior: interrogate one question at a time, write answers into harness files, do not produce the deliverable until context is sufficient. Produce session summary at end.
6. **Context window footer** — `pipeline/slack_format.py` helper that reads `WorkerManager.get_usage()`, computes percentage against `workspace.yaml.bot.model_context_window` (default 200_000), formats as `ContextActionsBlock` footer appended to every bot reply. Thresholds: 🟢 <40%, 🟡 40–85%, 🔴 >85%. Graceful fallback to "Context: unknown" if usage fetch fails.
7. **Customer feedback ingestion** — when a user replies to or reacts to a bot deliverable in `#intake`, dispatch to the Mechanic Agent's feedback operation. Proposal lands in `mechanic-log/`.

**Definition of Done.** In the real dogfood workspace: post in intake → see eval gate behavior → see context % on every reply → invoke a deliberately thin scenario → see grill-me fire → confirm grill-me writes to harness files → close session → see mechanic-log entry.

---

### P5 — Observability & Supervision

**Goal.** Listener runs unattended under systemd. Logs are structured and queryable by `run_id`. Operators get paged on crashes.

**REQUIREMENTS.md items closed:**
- Listener runs under systemd (`Restart=always`, `OOMPolicy=continue`, memory limit)
- All log lines structured JSON with correlation fields via `LoggerAdapter`
- Prometheus metrics endpoint (minimum set)
- Error reporting wired to Sentry (optional via `SENTRY_DSN` env var)
- Every session traceable end-to-end via `run_id`

**Work items.**
1. `pipeline/logging_setup.py` — JSON formatter + context-var-driven `LoggerAdapter` injecting `run_id`, `user_id`, `channel_id`, `phase`. Sweep the codebase to use it.
2. Prometheus — `prometheus_client` HTTP server on listener startup. Metrics: active sessions, outcomes, duration histograms, token/cost counters, error counters, PR counter.
3. Sentry — gated on `SENTRY_DSN`; scrubbing via `before_send` hook.
4. Systemd unit template at `docs/templates/chat-force@.service` and `scripts/install-bot.sh`.

**Definition of Done.** `journalctl -u chat-force@<slug>` shows JSON. `curl host:9109/metrics` shows counters. Killed PID → systemd restarts → P2 reconciliation reattaches containers.

**Parallelizable with.** P6 (different skills — code vs content).

---

### P6 — First Customer Harness Population

**Goal.** One real customer harness repo exists, populated, and validates.

**REQUIREMENTS.md items closed:**
- One harness repo with all required files per `docs/harness-schema.md`
- `workspace.yaml` populated with real values
- `slack-manifest.json` populated with real customer branding
- `identity/` files written (mission, brand, avatar, never-list, bot-persona)
- `eval/criteria.yaml` populated with customer's definition of "good"
- `vault/` initialized from template
- `mechanic-log/` directory exists
- Slack App created from manifest, tokens in Doppler
- Four channels created per customer, IDs in `workspace.yaml`

**Work items.**
1. Pick first customer — recommend `harness-travis-personal` as dogfood, THEN `harness-black-tie` as first real customer.
2. `git init harness-<slug>` as sibling repo; layout per schema.
3. Copy `docs/templates/slack-manifest.json` and `docs/templates/vault-starter/` into place; copy `docs/templates/skills/grill-me.md` as the starter skill.
4. Author `identity/` files and `eval/criteria.yaml` (content work — by Travis or with Anna).
5. Fill `workspace.yaml` with real values.
6. Create Slack App from manifest via `docs/templates/README.md` flow.
7. Set up Doppler config; set tokens.
8. Create four channels in Travis's Slack workspace; copy IDs back into `workspace.yaml`.
9. `HarnessLoader --validate <harness-path>` exits 0.

**Definition of Done.** HarnessLoader validates. Slack App installed. Channels exist. `workspace.yaml` fully populated.

**Parallelizable with.** P5 (observability).

---

### P7 — Production Cutover & Smoke

**Goal.** Real customer message produces real deliverable and real mechanic-log entry, on production host, under systemd.

**REQUIREMENTS.md items closed:**
- Slow integration suite green on merge to main (final run)
- End-to-end path closed: intake → session → deliverable → mechanic-log proposal
- All Part 2 capabilities verified in production

**Work items.**
1. Production host prep: Doppler installed, chat-force at `/opt/chat-force`, harness at `/var/lib/chat-force/harnesses/harness-<slug>`, state + runs dirs.
2. `scripts/install-bot.sh <slug>` → systemd unit enabled and started.
3. Smoke run — Travis posts in `#<slug>-intake`, observes session, gets deliverable, reviews mechanic-log entry, approves.
4. Final CI slow-tier run on `main`; tag commit `v1.0-first-customer`.
5. Write 1-page customer quick-reference into the harness `README.md`.

**Definition of Done.** First real deliverable exists on disk. First real mechanic-log entry reviewed and merged. Structured logs flowing. Metrics non-zero.

**Parallelizable with.** Nothing — this is the finish line.

---

## Parallelization Opportunities

| Track | Runs alongside | Notes |
|---|---|---|
| Context-window visibility | P0, P1, P2, P3 | Independent surface; merges into P4 |
| P3 Security (second half) | P2 Persistence (second half) | Different files once reconciliation lands |
| P5 Observability | P6 Harness population | Code vs content, different skills |

## Items Deferred Past v1

Called out here so they're visible but NOT in scope for first customer live:

- **Mechanical eval rule engine** (regex/url_check/length/custom) — v1 uses LLM-judge via Mechanic Agent against `eval/criteria.yaml` narrative
- **Vault ingest/query/lint operations** as full pipelines — v1 has the directory structure + read access + schema doc, but the operations are implemented iteratively in v1.1 as sessions accumulate
- **Per-day rolling budget cap** — v1 enforces per-session hard cap only
- **Second customer harness** — zero-code add after first customer is live
- **Dashboards over metrics** (Grafana, alerting rules) — `curl /metrics` is enough for v1
- **Local harness / portable sandbox** — Claude Code CLI running on customer's workstation, cloud-connected (not offline), with access to local hardware (USB, serial, JTAG debuggers, Raspberry Pi on LAN, local build systems). Boundary interface logs all local-resource access. Telemetry streams back to the factory; artifacts flow to the Mechanic; the feedback loop is fully intact. Two harness types: cloud-only (Slack + Docker, marketing clients) and local-execution (CLI + hardware + cloud connection, embedded engineering clients). Same harness schema + artifact format + mechanic loop. A real embedded client is waiting. v1 architecture must not foreclose: artifact format must not assume Docker, Mechanic must not assume Slack events, harness schema must remain deployment-agnostic. See REQUIREMENTS.md Part 4 for details.
- All items already in REQUIREMENTS.md Part 4 (LangGraph, horizontal scaling, cross-customer knowledge, etc.)

## How to Update This File

- When a phase completes, mark it ✅ here and check off its items in REQUIREMENTS.md Part 1
- When reality diverges from the plan, update the plan — don't let it become stale
- When a deferred item gets pulled in, move it from the deferred list into the appropriate phase
- This file and REQUIREMENTS.md stay in lockstep. If they disagree, REQUIREMENTS.md is the target and this file is the path; update the path.
