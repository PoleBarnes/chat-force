# Requirements

This file answers two questions for the orchestrator agent:
1. **What must be true for the system to be "done"?** (Product DoD)
2. **What must every change meet to be "done"?** (Feature DoD)

It does NOT track sprint tasks, timelines, or historical progress. Current work state lives in the agent's task list and in git commits. This file is stable — it changes only when the bar changes, not when work completes.

**Read this alongside [`CLAUDE.md`](CLAUDE.md) (the rules), [`factory-blueprint.md`](factory-blueprint.md) (the vision), and [`docs/architecture.md`](docs/architecture.md) (the shape).**

---

## Part 1 — Product Definition of Done

These are the items that must be true before the first customer deployment goes live. Every item is binary — it either passes or it doesn't. The system is done when every checkbox is checked.

### Engine / Harness Architecture

- [ ] Engine loads a harness from `HARNESS_PATH` env var
- [ ] `HarnessLoader` validates all required files at startup, fails loud with exact paths on any missing/invalid piece
- [ ] Engine code contains zero customer-specific content (no persona, no skills, no eval criteria hardcoded)
- [ ] `worker/Dockerfile` does not bake customer files into the image; harness is mounted/copied at runtime
- [ ] All four required harness sections are wired end-to-end: `identity/`, `eval/`, `skills/`, `mechanic-log/`
- [ ] `workspace.yaml` schema is parsed and applied (channel IDs, access allowlist, limits, git identity, token env var references)

### First Customer Harness (dogfood target or first paying customer)

- [ ] One harness repo exists with all required files per `docs/harness-schema.md`
- [ ] `workspace.yaml` populated with real values
- [ ] `slack-manifest.json` populated with real customer branding
- [ ] `identity/` files written (mission, brand, avatar, never-list, bot-persona)
- [ ] `eval/criteria.yaml` populated with customer's definition of "good"
- [ ] `vault/` initialized from `docs/templates/vault-starter/` and `VAULT.md` schema present
- [ ] `mechanic-log/` directory exists (engine can write to it)

### Slack Integration

- [ ] Slack App created from the harness's `slack-manifest.json`
- [ ] Bot token (`xoxb-`) and app token (`xapp-`) stored in Doppler under the customer's namespace
- [ ] Four channels created per customer: `#<slug>-intake`, `#<slug>-floor`, `#<slug>-mechanic-log`, `#<slug>-assets`
- [ ] Channel IDs written into `workspace.yaml`
- [ ] Listener routes messages differently based on channel role (intake has eval gate; floor allows free prototyping; mechanic-log is engine-write-only; assets is knowledge base)
- [ ] User allowlist enforced — unauthorized Slack users cannot trigger the bot

### Correctness

- [ ] Multi-turn conversation works end-to-end (send message → receive response → send follow-up → receive second response) with zero race conditions
- [ ] Session state survives listener restart (persisted to SQLite or equivalent; reconciled against `docker ps` on boot)
- [ ] Approved verdicts persist to disk immediately so they survive a crash between approval and PR creation
- [ ] Mechanic Agent uses structured output for verdicts (no fragile JSON text parsing)
- [ ] Mechanic parse failures surface as distinct error state, not silent rejection storms
- [ ] Worker crash produces `/tmp/worker-error.txt`; host surfaces the error to the user within seconds, not minutes
- [ ] `wait_for_completion` timeout actually kills the container before raising

### Security (all Critical findings from review must be fixed)

- [ ] Slack user allowlist enforced at handler entry
- [ ] `ANTHROPIC_API_KEY` scoped/isolated from the user-controlled Worker sandbox (or proxied)
- [ ] `GITHUB_TOKEN` never embedded in command-line URLs, never logged; uses credential helper
- [ ] Worker container runs with `cap_drop=ALL`, `no-new-privileges`, `mem_limit`, `cpu_quota`, `pids_limit`
- [ ] Worker has restricted egress (allowlist of necessary domains, not full internet)
- [ ] `.github/workflows/`, `worker/Dockerfile`, `pipeline/`, `mechanic/` are on a deny-list for worker modifications
- [ ] Changeset extractor uses list-form subprocess calls, not shell interpolation; path traversal rejected in `PRCreator._write_file`
- [ ] Secret scanner (gitleaks/trufflehog) runs on every changeset before PR creation; any finding blocks the PR
- [ ] Exception messages surfaced to Slack are scrubbed of tokens and sensitive data

### Reliability / Operations

- [ ] Listener runs under systemd (`Restart=always`, `OOMPolicy=continue`, explicit memory limit)
- [ ] Every external call (Claude API, Docker API, GitHub API, Slack API) has retry with exponential backoff on transient errors
- [ ] `max_budget_usd`, `max_turns`, `IDLE_TIMEOUT` are plumbed from `workspace.yaml` into the Worker container env (no hardcoded defaults silently applied)
- [ ] Disk cleanup thread runs hourly; `/var/lib/chat-force/runs/` older than N days is pruned
- [ ] Container reconciliation on listener startup — orphans from prior runs are identified and either reattached or force-removed
- [ ] Global concurrency cap enforced via semaphore — single user cannot spawn unlimited containers

### Observability

- [ ] All log lines structured (JSON), with `run_id`, `user_id`, `channel_id`, `container_id`, `phase` fields via a `LoggerAdapter`
- [ ] Prometheus metrics endpoint exposed on the listener process: active sessions, session outcomes by status, worker/mechanic duration histograms, token/cost counters, error counters by phase, PR creation counter
- [ ] Error reporting wired to Sentry (or equivalent); uncaught exceptions page an operator
- [ ] Every session traceable end-to-end via `run_id` (Slack message → session → worker → changeset → mechanic verdict → PR or fix proposal)

### Testing / CI

- [ ] Fast test suite (`-m "not slow"`) runs on every push; green is required to merge
- [ ] Slow integration suite (real Docker + real Claude API + real GitHub) runs on merge to `main`
- [ ] CI workflow refuses to merge if any tier fails
- [ ] Every `pipeline/`, `worker/`, or harness contract change has test coverage at the right tier (unit for logic, integration for boundaries, real-service for external APIs)
- [ ] Test pyramid has no fossil tests (tests that enforce shapes the code no longer has)

### Vibe Code Loop (front of house)

- [ ] User posts in `#<slug>-intake` → engine creates session → bot collaborates in `#<slug>-floor` → deliverable ships
- [ ] The bot has read access to the harness `vault/` and uses it for context
- [ ] Deliverables land in the configured backend (filesystem, Google Drive, etc.) per `workspace.yaml.deliverables`
- [ ] Eval mechanical checks run on output before it leaves `#intake`

### Mechanic Loop (back of house)

- [ ] After each session, the Mechanic Agent analyzes the session transcript + tool log + eval criteria
- [ ] Mechanic Agent writes structured fix proposals to `harness/mechanic-log/<date>-<slug>.md`
- [ ] Proposals surface in `#<slug>-mechanic-log` channel for human review
- [ ] Human-approved fixes land in the harness via PR (to `skills/`, `eval/`, or persona files)
- [ ] The Mechanic Agent never auto-installs fixes — approval gate is enforced

---

## Part 2 — Non-Negotiable Capabilities

These are the load-bearing walls. Remove any of them and the system is no longer chat-force. They change rarely, if ever.

1. **Multi-turn conversation.** A single Slack thread can carry on indefinitely with the bot, maintaining context across messages, until idle timeout or explicit close.

2. **Per-customer isolation.** Customer A's bot, harness, vault, secrets, and mechanic log never touch customer B's. Cross-customer knowledge transfer only happens via explicit human action.

3. **Eval gate on deliverables.** Nothing leaves `#intake` to the customer without passing the mechanical eval checks declared in the harness `eval/criteria.yaml`.

4. **Mechanic loop with human approval.** Every improvement to the harness (skills, eval, persona) goes through a proposal → human review → install flow. The AI never commits directly.

5. **Crash recoverability.** The listener process can restart (crash, deploy, OOM) without losing active sessions or orphaning containers.

6. **Complete audit trail.** Every session transcript, every tool call, every mechanic verdict, every fix proposal is persisted and queryable by `run_id`.

7. **Per-bot budget enforcement.** No single customer's sessions can exceed their declared `max_budget_usd` or daily cap. Cost runaway is impossible, not just discouraged.

8. **Secret hygiene.** Tokens never appear in logs, command-line arguments, URLs, exceptions forwarded to Slack, or persisted changesets. Ever.

9. **Container-scoped privilege.** The Worker container is sandboxed — no host access, no Docker socket, capped resources, restricted egress. `bypassPermissions` is only safe because the sandbox is real.

10. **Spec before code.** Every feature begins as a written spec (what it does, what it doesn't, failure modes). No code ships without its spec and its tests.

---

## Part 3 — Feature Definition of Done

Every code change — from a one-line fix to a new subsystem — must meet every item on this list before it ships. No exceptions for "it's just a small fix."

1. **Spec written first.** The change's purpose and scope are documented (in a plan file, a PR description, or a design doc). Failure modes considered up front.

2. **Tests written first.** Per `CLAUDE.md` TDD rules. Test fails before the fix; passes after.

3. **Right test tier.** Unit tests for pure logic. Integration tests for anything that crosses a boundary (Docker, Claude, GitHub, Slack, filesystem). Real-service tests for external API behavior that mocks can't catch.

4. **All tests green.** Full fast suite passes before commit. Slow suite passes before merge to `main`.

5. **Reviewed.** Codex CLI review pass for code changes of any substance. Architect or explore agent review for anything touching cross-cutting concerns (security, concurrency, observability, data integrity).

6. **Observable.** If the feature matters in production, it emits structured logs with correlation IDs. If it's on the hot path, it emits a metric.

7. **Failure modes handled explicitly.** No bare `except`, no silent swallow. Every external call has a retry or a loud failure path. Transient vs permanent errors distinguished.

8. **Docs reflect reality.** If the change affects the harness contract, `docs/harness-schema.md` updated. If it affects the runtime contract, `CLAUDE.md` updated. If it affects the architecture, `docs/architecture.md` updated.

9. **No new tech debt.** No TODOs, no FIXMEs, no "we'll fix this later" comments. If it's worth doing, do it; if not, don't introduce it.

10. **Doesn't break anything.** `git status` clean at commit time (no unintended changes). Full test suite passes. Existing customers' harnesses still load without modification.

---

## Part 4 — Out of Scope (Explicitly Not Required)

YAGNI applies. These are things that sound useful but are NOT required for first customer deployment. Don't build them unless a concrete customer need forces them.

- **LangGraph / structured workflows.** Skills alone should get us most of the way. Reintroduce rigidity only when skills prove insufficient.
- **Multi-host deployment / horizontal scaling.** Single host with multiple systemd units per bot is fine until we outgrow one box.
- **Cross-customer knowledge transfer.** Manual operation by the human mechanic until we have enough customers to justify the observability layer.
- **Meta-Mechanic / Scout / Mechanic B.** Deferred. The single Mechanic Agent handles per-session analysis; other roles are future work.
- **Custom UI beyond Slack.** Slack is the interface. No dashboards, no web apps, no mobile clients in v1.
- **Token rotation automation.** Manual rotation via Doppler is fine until we're at 5+ bots.
- **Per-bot Anthropic API keys.** One shared key with per-bot budget tracking is enough for v1.
- **Embeddings / RAG inside the vault.** Read-the-whole-index works at 100–1000 pages. Defer until a customer vault outgrows that.

If a task surfaces that falls into this list, the right answer is "not now" — not "quickly."

---

## How To Use This File

**As the orchestrator agent:**
- Before starting work, check Part 1 — find the next unchecked item
- When proposing work, verify it advances a Part 1 item or is required by Part 2
- When reviewing a PR, apply Part 3 as the gate
- When asked to add a feature, first check Part 4 — it may be explicitly out of scope

**As Travis:**
- Check a box in Part 1 when an item is complete
- Update Part 2 only if a load-bearing capability changes
- Update Part 3 only if the bar for "done" changes
- Update Part 4 when you decide something new is not-yet-needed

**This file is the orchestrator's compass. If it's wrong, the system is pointed wrong.**
