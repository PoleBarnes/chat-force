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
- [ ] Every Mechanic fix proposal includes a `test_proposal` block (skill scenario, eval fixture, regression scenario, script, or documented manual check). Proposals without one are rejected.
- [ ] Proposals surface in `#<slug>-mechanic-log` channel for human review
- [ ] Human-approved fixes land in the harness via PR (to `skills/`, `eval/`, or persona files)
- [ ] The Mechanic Agent never auto-installs fixes — approval gate is enforced
- [ ] Customer feedback ingestion: any customer reaction or reply to a deliverable triggers a Mechanic operation that analyzes the feedback and proposes eval/identity updates (`mechanic-log/<date>-feedback-*.md`)
- [ ] Vault lint: scheduled Mechanic pass walks the vault for orphans, stale claims, contradictions; writes `mechanic-log/<date>-vault-lint.md` for human review

### Customer Intake / Grill-Me

- [ ] `docs/templates/skills/grill-me.md` copied into every new harness as `skills/grill-me.md`
- [ ] Engine intake handler invokes grill-me whenever: (a) the customer posts in `#intake` for the first time with thin harness identity/eval, (b) the customer asks for a deliverable that requires context the harness does not yet hold, or (c) mechanic-log flagged a missing field from a prior session
- [ ] Grill-me asks one question at a time with a recommended answer, walks the decision tree (business → mission → voice → avatar → assets → eval → deliverable-specific), and writes confirmed answers back into the harness in real time
- [ ] Grill-me explores the harness/vault/brand-assets before asking — blank questions are forbidden
- [ ] Every grill session produces a summary page at `vault/summaries/sessions/<date>-grill-<topic>.md`

### Context Window Visibility

- [ ] Every bot response in a session displays the current context window usage as a percentage
- [ ] Threshold indicators: 🟢 under 40%, 🟡 40–85%, 🔴 above 85% — so the user knows when to close the session
- [ ] Implementation uses a `ContextActionsBlock` footer appended to every response (alongside feedback buttons), with percentage + turn count + cumulative cost
- [ ] Computed from `WorkerManager.get_usage()` (already exists) divided by the model's context window (`workspace.yaml.bot.model_context_window`, default 200_000)
- [ ] Gracefully degrades if `get_usage()` fails — shows "Context: unknown" rather than crashing the response

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

11. **Grill before building.** When the harness does not have enough context to produce a good deliverable for what the customer is asking, the bot grills the customer to fill in the missing context before attempting the work. Thin harness → thin work → broken trust. Fix the harness first.

12. **Feedback feeds the eval.** Every customer reaction to a deliverable — thumbs, text, rework requests, silence — becomes a data point the Mechanic Agent mines for eval/identity updates. Feedback is not discarded; it is the highest-quality training signal the system receives.

13. **TDD at every layer.** Code changes follow TDD per `CLAUDE.md`. Harness changes (skills, eval, personas) proposed by the Mechanic Agent include a `test_proposal` block specifying how a regression of the fix would be detected. No test = no merge, no install, no ship.

14. **Context visibility.** The user sees current context window usage on every bot turn, as a clear percentage with threshold indicators, so they can make informed decisions about when to close out a session.

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
- **Local harness / portable sandbox.** Some customers (embedded engineering) need the bot to run on their local machine with access to hardware debuggers, USB devices, local build systems, and other resources that can't be exposed over a network. This requires a "local mode" where Claude Code CLI runs directly on the developer's workstation (not in a Docker container), with a boundary interface that logs all local-resource access, and session capture that produces the same standardized artifact as the hosted mode so the Mechanic can analyze it identically. The cloud harness (Slack + Docker, marketing customers) and local harness (CLI + hardware, engineering customers) share the same harness schema, the same artifact format, and the same mechanic loop — they differ only in execution environment. A real embedded engineering client is waiting for this, but it is explicitly post-v1. **The v1 architecture must not foreclose on this** — specifically: the artifact format must not assume Docker, the Mechanic must not assume Slack events, and the harness schema must remain deployment-agnostic. See `Portable_Sandbox_Requirements.docx` for the full requirements brainstorm.

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
