# P0 — Engine / Harness Split

**Status:** Complete (7 commits on pivot/agent-sdk, 228 fast tests green)
**Owner:** Travis
**Target branch:** `pivot/agent-sdk`
**Completes:** ROADMAP P0; REQUIREMENTS.md Part 1 "Engine / Harness Architecture" section

This spec is the execution contract for P0. It describes *what* gets built, *why*, and *how it's verified*. It does not describe the full vision — read `REQUIREMENTS.md`, `factory-blueprint.md`, `docs/architecture.md`, `docs/harness-schema.md` for that context. This spec assumes all of those are already understood.

---

## 1. Goal

After P0, `python -m pipeline.slack_listener`:

1. Refuses to start without `HARNESS_PATH` (exits 1 with the canonical error)
2. Loads and validates an external harness directory at startup via `HarnessLoader`
3. Passes every customer-specific value (bot name, tokens, limits, identity content, eval criteria, git identity) through a typed `LoadedHarness` object, not hardcoded constants
4. Contains **zero** customer-specific strings in `pipeline/`, `worker/`, or `mechanic/` code

The Worker container receives the harness as a bind mount at `/harness` and reads identity/skills from there instead of from files baked into the image.

## 2. Non-Goals (deferred past P0)

Listed so scope creep is visible:

- Per-harness PR routing (the engine still PRs to `PoleBarnes/chat-force` for its own self-improvement flow; customer PRs to harness repos are P1+)
- Fine-grained bind-mount permissions (`identity/` r/o, `vault/` r/w at the FS layer). P0 bind-mounts the entire harness r/w; enforcement is a P3 security hardening concern.
- Egress restriction, gitleaks, self-modification deny-list → **P3**
- Channel role routing (`#intake` vs `#floor` vs `#mechanic-log`) → **P4**
- Context window percentage footer → **P4**
- Mechanic structured output Pydantic verdict model end-to-end → **P1** (the mechanic prompt gets `eval/criteria.yaml` injected in P0, but verdict parsing improvements are P1)
- Vault read/write hooks, vault lint operation → **P4**
- SQLite session persistence, container reconciliation → **P2**
- Pulling `github_repo` / `pr_branch_prefix` from the harness → **P1**

Anything matching an item on this list must not land in P0. If it needs to happen to unblock P0, stop and escalate.

---

## 3. Architecture: engine vs harness split at the code layer

Two peer config objects flow through every manager:

### 3.1 `PipelineConfig` (engine-global, shrinks)

Still exists. Still carries engine-global tunables:

- `worker_image`, `docker_network`, `output_base` (Docker runtime)
- `worker_timeout`, `mechanic_timeout` (hard kill defaults — may move to harness in P1)
- `pr_branch_prefix`, `github_repo`, `github_token_env`, `config_repo_url` (engine self-improvement PR flow — stays until P1)
- `claude_code_token_env` (shared `ANTHROPIC_API_KEY`; per-bot keys are deferred)
- `allowed_tools`, `permission_mode` (engine-chosen defaults; may move to harness later)

**Removed from `PipelineConfig`:** nothing in P0. Fields that become harness-driven are accessed via the `harness` field added below.

**New field on `PipelineConfig`:** `harness: LoadedHarness | None = None`. Set once by `slack_listener.main()` after a successful load. Every manager that currently takes `(config, run_id)` continues to do so; the harness rides along as `config.harness`.

### 3.2 `LoadedHarness` (new)

A frozen, in-memory snapshot of one harness directory. Lives in `pipeline/harness_loader.py`. Shape:

```python
@dataclass(frozen=True)
class LoadedHarness:
    harness_path: Path                     # absolute path to harness root
    workspace: WorkspaceConfig             # pydantic model (see §4)
    identity: IdentityBundle               # five markdown files loaded to strings
    eval_criteria: EvalCriteria            # parsed eval/criteria.yaml
    # Convenience accessors for common fields
    @property
    def slug(self) -> str: ...
    @property
    def bot_name(self) -> str: ...         # workspace.bot.display_name
    @property
    def bot_token_env(self) -> str: ...    # workspace.bot.slack_bot_token_env
    @property
    def app_token_env(self) -> str: ...    # workspace.bot.slack_app_token_env
```

### 3.3 How they flow

```
slack_listener.main()
  ├─ HarnessLoader.load(resolve_path())  → LoadedHarness
  ├─ PipelineConfig(harness=loaded)      → config
  └─ create_app(config)
       └─ SessionManager(config)
            └─ WorkerManager(config, run_id)        # reads config.harness
            └─ MechanicManager(config, run_id)      # reads config.harness
            └─ ChangesetExtractor(config, run_id)   # reads config.harness
            └─ PRCreator(config, run_id)            # reads config.harness (git identity)
```

Constructors do NOT grow an extra `harness` parameter. They read `config.harness`. This keeps the refactor minimal and keeps the fact that "harness is part of the runtime config" visible.

---

## 4. Pydantic models for `workspace.yaml`

All models are Pydantic v2, `BaseModel`, `model_config = ConfigDict(extra="forbid", frozen=True)`. One model per §3 sub-section of `docs/harness-schema.md`.

```python
# pipeline/harness_loader.py (subset shown)

SLUG_PATTERN = r"^[a-z0-9-]+$"
SLACK_CHANNEL_PATTERN = r"^C[A-Z0-9]{8,}$"

class BotConfig(BaseModel):
    display_name: str = Field(min_length=1)
    avatar_path: str | None = None
    slack_app_id: str | None = None
    slack_bot_token_env: str = Field(min_length=1)
    slack_app_token_env: str = Field(min_length=1)

class GitConfig(BaseModel):
    user_name: str = Field(min_length=1)
    user_email: str = Field(min_length=1)
    github_token_env: str | None = None
    github_username: str | None = None

class ChannelsConfig(BaseModel):
    intake: str = Field(pattern=SLACK_CHANNEL_PATTERN)
    factory_floor: str = Field(pattern=SLACK_CHANNEL_PATTERN)
    mechanic_log: str = Field(pattern=SLACK_CHANNEL_PATTERN)
    brand_assets: str = Field(pattern=SLACK_CHANNEL_PATTERN)

class AccessConfig(BaseModel):
    allowed_user_ids: list[str] = Field(min_length=1)

class LimitsConfig(BaseModel):
    max_concurrent_sessions: PositiveInt
    max_budget_usd_per_session: PositiveFloat
    max_budget_usd_per_day: PositiveFloat
    max_turns_per_session: PositiveInt
    session_idle_timeout_seconds: PositiveInt
    worker_timeout_seconds: PositiveInt
    mechanic_timeout_seconds: PositiveInt

class FilesystemDeliverableConfig(BaseModel):
    path: str = Field(min_length=1)

class DeliverablesConfig(BaseModel):
    backend: Literal["filesystem"]            # only "filesystem" in P0
    filesystem: FilesystemDeliverableConfig

class WorkspaceConfig(BaseModel):
    schema_version: Literal[1]
    slug: str = Field(pattern=SLUG_PATTERN, max_length=32)
    bot: BotConfig
    git: GitConfig
    channels: ChannelsConfig
    access: AccessConfig
    limits: LimitsConfig
    deliverables: DeliverablesConfig
```

**`eval/criteria.yaml`** gets a simpler Pydantic model:

```python
class EvalCheck(BaseModel):
    id: str
    description: str
    type: Literal["llm_judge", "regex", "url_check", "length", "custom"]
    pattern: str | None = None
    must_not_match: bool | None = None

class EvalCriteria(BaseModel):
    schema_version: Literal[1]
    narrative: str
    checks: list[EvalCheck] = Field(default_factory=list)
```

`IdentityBundle` is a plain dataclass carrying the five `.md` files as strings (`mission`, `brand`, `avatar`, `never_list`, `bot_persona`). No validation beyond "file exists and is readable"; content is freeform markdown.

---

## 5. `HarnessLoader` API

```python
class HarnessValidationError(Exception):
    """Raised when a harness fails to load. Always names path + field."""

class HarnessLoader:
    @staticmethod
    def resolve_path(cli_flag: str | None = None) -> Path:
        """
        Resolution order:
        1. --harness-path CLI flag (if provided)
        2. HARNESS_PATH env var
        3. Raise HarnessValidationError with the canonical "HARNESS_PATH required" message.
        """

    @staticmethod
    def load(harness_path: Path) -> LoadedHarness:
        """
        Full load + validate sequence per docs/harness-schema.md §6:
        1. Verify path exists and is a directory
        2. Load + validate workspace.yaml via WorkspaceConfig
        3. Verify required secret env vars exist
        4. Verify required directories exist (identity/, eval/, skills/, mechanic-log/, vault/)
        5. Verify required files exist (identity/*.md × 5, eval/criteria.yaml, vault/VAULT.md, vault/index.md, vault/log.md)
        6. Load identity files into IdentityBundle
        7. Load + validate eval/criteria.yaml into EvalCriteria
        8. Return LoadedHarness

        Any failure raises HarnessValidationError with §7 canonical message.
        Never partial-loads.
        """
```

---

## 6. Error taxonomy — the contract with harness-schema §7

Every error maps 1:1 to a row below. These strings are tested literally.

| Condition | Canonical message |
|---|---|
| `HARNESS_PATH` unset and no `--harness-path` flag | `HARNESS_PATH environment variable is required. Set it to an absolute path to a harness repository.` |
| Path does not exist | `Harness path does not exist: <path>` |
| Path exists but not a directory | `Harness path is not a directory: <path>` |
| `workspace.yaml` missing | `Required file missing: <path>/workspace.yaml` |
| `workspace.yaml` malformed YAML | `workspace.yaml parse error: <parser message>` |
| `workspace.yaml` Pydantic validation failure | `workspace.yaml invalid at field "<field>": <reason>. Expected: <expected>. Got: <got>.` |
| Required env var missing | `Required secret env var missing: <name> (referenced by workspace.yaml <path>)` |
| Required identity file missing | `Required identity file missing: <path>/identity/<name>.md` |
| `eval/criteria.yaml` missing | `Required file missing: <path>/eval/criteria.yaml` |
| `eval/criteria.yaml` malformed YAML | `eval/criteria.yaml parse error: <parser message>` |
| `eval/criteria.yaml` Pydantic validation failure | `eval/criteria.yaml invalid at field "<field>": <reason>. Expected: <expected>. Got: <got>.` |
| Required directory missing | `Required directory missing: <path>/<dir>` |

`HarnessLoader` catches `pydantic.ValidationError` once per validated file, walks `err.errors()`, and re-raises `HarnessValidationError` formatted to the appropriate schema-mismatch row above (one for `workspace.yaml`, one for `eval/criteria.yaml`). All field/path interpolation happens at the single validator call site.

---

## 7. Worker container contract changes

### 7.1 Mount topology

**Before:**
```
Image baked: /workspace/config/{SOUL,IDENTITY,USER,AGENTS}.md  (COPY at build)
Runtime cwd: /workspace/config
```

**After:**
```
Image baked: nothing customer-specific
Runtime bind mount: <harness_path> → /harness   (rw in P0; granular perms deferred)
Runtime cwd: /harness
```

The writable git-backed workspace for changeset extraction moves from `/workspace/config` to `/harness`. `ChangesetExtractor` must read from the new path. The `worker/entrypoint.py` runs `git init && git add -A && git commit -m baseline` inside `/harness` at startup if not already a repo.

### 7.2 System prompt assembly

`worker/entrypoint.py:build_system_prompt()` now reads:

```
/harness/identity/mission.md       → "# MISSION\n..."
/harness/identity/brand.md         → "# BRAND\n..."
/harness/identity/avatar.md        → "# AVATAR\n..."
/harness/identity/never-list.md    → "# NEVER\n..."
/harness/identity/bot-persona.md   → "# PERSONA\n..."
```

Concatenated in that order. Skills in `/harness/skills/` are NOT preloaded into the system prompt — the worker reads them on demand via the `Read` tool (matches current Claude Code idiom).

### 7.3 Env vars from `harness.limits`

`WorkerManager.start()` sets these container env vars from `harness.workspace.limits`:

```
MAX_TURNS            = max_turns_per_session
MAX_BUDGET_USD       = max_budget_usd_per_session
IDLE_TIMEOUT         = session_idle_timeout_seconds
WORKER_CWD           = /harness                       # (constant in P0, but declared)
```

`worker/entrypoint.py` currently reads `MAX_TURNS` and `MAX_BUDGET_USD` from env with defaults. In P0, the defaults are removed — if any required env var is missing, the entrypoint crashes loud with `worker-error.txt`.

---

## 8. Engine refactor manifest

One-line summary per file. Every file on this list is touched in P0; nothing else.

| File | Change |
|---|---|
| `pipeline/harness_loader.py` | **NEW.** `HarnessLoader`, `LoadedHarness`, Pydantic models, `HarnessValidationError`. |
| `pipeline/config.py` | Add `harness: LoadedHarness | None = None` field. No other changes. |
| `pipeline/slack_listener.py` | `main()` loads harness; exits 1 loudly on failure; reads `SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN` via `harness.bot_token_env` / `harness.app_token_env`. `create_app()` parameterizes all "Leo" strings via `bot_name = config.harness.bot_name`. ~30 string replacements. |
| `pipeline/session_manager.py` | Reads `session_idle_timeout` from `config.harness.workspace.limits.session_idle_timeout_seconds`. |
| `pipeline/worker_manager.py` | `start()` passes `-v <harness_path>:/harness` bind mount. Sets container env from `config.harness.workspace.limits`. Drop "Leo" from docstrings. Drop the `git rev-parse HEAD` image-ratchet tagging (image content no longer depends on engine git state). |
| `pipeline/mechanic_manager.py` | `evaluate()` prepends `config.harness.eval_criteria.narrative` + the checks list to the mechanic prompt. Universal `mechanic/config/*.md` loading unchanged. |
| `pipeline/changeset_extractor.py` | Replace hardcoded `/workspace/config` with `/harness` (or a single `WORKER_CWD` constant). |
| `pipeline/pr_creator.py` | Uses `config.harness.workspace.git.user_name` / `user_email` for the commit author. `github_repo`/`github_token_env` stay engine-global in P0. |
| `pipeline/main.py` | CLI `--harness-path` flag added; required if `HARNESS_PATH` unset. Drop any "Leo" string. |
| `pipeline/slack_handler.py` | Untouched unless it contains "Leo" strings (check + scrub if so). |
| `pipeline/requirements.txt` | Add `pydantic>=2` line. |
| `worker/Dockerfile` | Delete all `COPY docker/config/workspace/*.md`. Delete the `git init /workspace/config` baseline. Image becomes: python base + `apt install git curl` + `pip install claude-agent-sdk` + `COPY worker/entrypoint.py`. No customer content. |
| `worker/entrypoint.py` | `build_system_prompt()` reads from `/harness/identity/*.md` per §7.2. `WORKSPACE_CWD` → reads from `WORKER_CWD` env (defaults `/harness`). Required limit envs crash loud if missing. Baseline git init moves here. |

---

## 9. Slack listener "Leo" string scrub list

These strings in `pipeline/slack_listener.py` become parameterized. The variable is `bot_name = config.harness.bot_name` set once at the top of `create_app()`.

Approximate list (line numbers from the current file; Codex verifies and scrubs exhaustively):

- L226 `"Hey! I'm Leo — your digital worker..."` → `f"Hey! I'm {bot_name} — tell me what you need and I'll get to work."`
- L280 `"Leo is thinking..."` → `f"{bot_name} is thinking..."`
- L285 `":hourglass: Timed out waiting for Leo..."` → `f":hourglass: Timed out waiting for {bot_name}..."`
- L294, L405, L466, L555, L636, L729, L787 `"_Leo didn't produce a response._"` → `f"_{bot_name} didn't produce a response._"`
- L306, L309, L374, L607, L640, L700 `"Leo is thinking..."` chunks → parameterized
- L345, L437, L442, L451, L471, L673, L760, L771, L792 various "Leo is working..." / "Leo finished" / "Leo encountered an error" → parameterized
- L571 docstring `@Leo mention` → `@<bot>`
- L1, L4 module docstring `"Slack socket-mode listener for Leo."` → `"Slack socket-mode listener for a chat-force bot."`

Also scrub the **suggested prompts** at L228-245: these are Leo-flavored starter prompts. Replace with generic prompts OR (preferred) read them from an optional `identity/suggested-prompts.md` file in the harness. **Out of P0 scope** — just replace with three generic prompts in P0 (`"Help me plan a task"`, `"Draft a short update"`, `"Ask me what I need"`). Suggested prompts from the harness is a P4 nice-to-have.

---

## 10. Fixture harness at `tests/fixtures/harness-fixture/`

Minimal-but-valid. Generic name `testbot` — no real customer references.

```
tests/fixtures/harness-fixture/
├── README.md                    # "Test fixture harness — do not edit without updating tests"
├── workspace.yaml               # slug: testbot, display_name: TestBot, env: TESTBOT_SLACK_BOT_TOKEN / TESTBOT_SLACK_APP_TOKEN
├── slack-manifest.json          # copied from docs/templates/slack-manifest.json, REPLACE_ME_* values intact
├── identity/
│   ├── mission.md               # "TestBot is a fixture persona for engine tests."
│   ├── brand.md                 # voice placeholder
│   ├── avatar.md                # ICP placeholder
│   ├── never-list.md            # "- Never contain real customer identifiers"
│   └── bot-persona.md           # "Neutral, factual, minimal flourish."
├── eval/
│   └── criteria.yaml            # schema_version: 1, one-line narrative, empty checks list
├── skills/
│   └── .gitkeep
├── mechanic-log/
│   └── .gitkeep
└── vault/
    ├── VAULT.md                 # copied from docs/templates/vault-starter/VAULT.md
    ├── index.md                 # empty catalog
    ├── log.md                   # empty log
    ├── raw/.gitkeep
    ├── summaries/sources/.gitkeep
    ├── summaries/sessions/.gitkeep
    ├── entities/.gitkeep
    ├── concepts/.gitkeep
    └── decisions/.gitkeep
```

`workspace.yaml` channel IDs use the pattern `C00TEST0000` (fake but matches the regex). All Slack user IDs use `U00TEST0000`.

---

## 11. Test strategy

### 11.1 New test file: `tests/test_harness_loader.py`

One test per row in §6. Plus:

- `test_load_happy_path` — valid fixture loads; every field populated
- `test_resolve_path_cli_flag_overrides_env` — flag wins over env var
- `test_resolve_path_env_var` — env var alone works
- `test_resolve_path_neither_set` — raises canonical error
- `test_identity_bundle_content` — all five files loaded as strings, non-empty
- `test_eval_criteria_parsed` — narrative + checks list populated from yaml

Tests are written FIRST per CLAUDE.md TDD. Each test must fail before `HarnessLoader` is implemented (ImportError or AttributeError is acceptable for "test fails because the thing doesn't exist yet").

### 11.2 New `tests/conftest.py`

```python
@pytest.fixture(scope="session")
def harness_fixture_path() -> Path:
    return Path(__file__).parent / "fixtures" / "harness-fixture"

@pytest.fixture(scope="session", autouse=True)
def _testbot_env(monkeypatch_session):
    # set fake secrets so HarnessLoader validation passes in every test
    os.environ["TESTBOT_SLACK_BOT_TOKEN"] = "xoxb-test-fixture"
    os.environ["TESTBOT_SLACK_APP_TOKEN"] = "xapp-test-fixture"
    yield
    # cleanup

@pytest.fixture
def loaded_harness(harness_fixture_path) -> LoadedHarness:
    return HarnessLoader.load(harness_fixture_path)

@pytest.fixture
def config_with_harness(loaded_harness, tmp_path) -> PipelineConfig:
    return PipelineConfig(output_base=str(tmp_path), harness=loaded_harness)
```

### 11.3 Existing test updates

Every test currently constructing `PipelineConfig(...)` directly migrates to `config_with_harness` (or constructs a harness inline if it needs to mutate values). Leo-specific assertions rewrite to `loaded_harness.bot_name`-based assertions.

Goal: **all 183 fast tests green** against the fixture harness. Test count may shift as stale tests (e.g., `test_pipeline.py` L2122-2142 reading `SOUL.md`/`IDENTITY.md`) get rewritten to read from the fixture's `identity/*.md`.

---

## 12. Deletion manifest

These paths are deleted in P0 (tracked in a single commit for clarity):

| Path | Reason |
|---|---|
| `skills/` (engine root, 7 files) | Leo-flavored starter skills; per Travis, each bot bootstraps its own skills from customer usage going forward |
| `docker/config/workspace/{SOUL,IDENTITY,USER,AGENTS,CRON}.md` | Leo persona content, now lives in per-harness `identity/` |
| `docker/config/slack-devbot-manifest.yaml` | Stale Leo-era Slack manifest; `docs/templates/slack-manifest.json` replaces it |
| `docker/config/` (whole tree if empty after above) | No remaining content |
| `tests/fixtures/ad-campaign-workflow.md` | Stale Leo task fixture |
| `tests/fixtures/blacktie-april-campaign.md` | Stale BlackTie task fixture |
| `tests/fixtures/blacktie-context.md` | Stale BlackTie context fixture |

Any test that references these fixtures either gets rewritten to use the fixture harness or deleted if the test no longer has reason to exist.

**NOT deleted in P0** (checked separately):

- `docs/harness-schema.md`, `ROADMAP.md`, `factory-blueprint.md` — use "black-tie", "mailbox-money" as illustrative examples in documentation. Staying. These are outside the grep scope (`pipeline/ worker/ mechanic/`).
- `docs/templates/slack-manifest.json` — `REPLACE_ME_*` placeholders, no customer content. Staying.
- `security/secret-injection.md`, `security/self-modification-guard.md` — verify contents don't hardcode customer strings; if they do, scrub (these are engine docs, not engine code).

---

## 13. P0 Definition of Done

All of the following must be true. Automated where possible.

1. `grep -riwE "leo|blacktie|mailbox|aaa-pure|usaf" pipeline/ worker/ mechanic/` returns **zero matches**. Word-boundary (`-w`) form is required; the naive substring grep has false positives on unrelated identifiers that happen to contain these letter sequences (e.g., Python stdlib `fileobj` contains `leo` as a substring).
2. `grep -riwE "leo|blacktie|mailbox|aaa-pure|usaf" tests/` returns matches **only under** `tests/fixtures/harness-fixture/` (none; fixture uses `testbot`). Same word-boundary requirement as above.
3. Fast test suite green: all tests under `tests/ -m "not slow"` pass against the fixture harness.
4. `HARNESS_PATH` unset → `python -m pipeline.slack_listener` exits 1 with the canonical `HARNESS_PATH environment variable is required...` message. Automated as a subprocess test.
5. `HARNESS_PATH` pointing at a copy of the fixture with `identity/brand.md` removed → listener exits 1 with `Required identity file missing: <path>/identity/brand.md`. Automated as a subprocess test.
6. `worker/Dockerfile` contains no `COPY docker/config/` lines. The worker image builds from the Dockerfile alone with no customer content inside.
7. `pipeline/requirements.txt` declares `pydantic>=2`.
8. Full test command with pydantic added to `--with` flag succeeds:
   ```
   HARNESS_PATH=tests/fixtures/harness-fixture \
   uv run --python 3.13 \
     --with docker,"slack_sdk>=3.41.0","slack_bolt>=1.27.0","pydantic>=2",pytest \
     pytest tests/ -m "not slow"
   ```

---

## 14. Review gates before merge

Per REQUIREMENTS.md Part 3:

1. **Codex CLI review** of the full P0 diff against this spec. Focus: correctness, exhaustive scrub of customer strings, root-cause handling (no silent `except`), error message literal match to §6 table.
2. **Explore agent review** of architecture adherence: is `LoadedHarness` actually the single source of customer-specific config? Are there leaks where a manager reads from `os.environ` directly instead of going through the harness? Does the worker container actually mount the harness as specified?
3. All tests green on both reviews.

Only after both review passes and green tests: squash-merge the P0 branch into `pivot/agent-sdk`.

---

## 15. Out-of-band verification before closing P0

Travis runs a smoke dogfood in his own workspace with a test harness (not the fixture — a real minimal harness named something like `harness-travis-personal` created by hand from the fixture). Posts a message, confirms the bot responds with the harness's `bot_name` (not "Leo") and produces a reasonable deliverable. If this smoke fails, P0 is not done.

This is not automated. It's the final human check that the abstraction actually holds end-to-end with real Docker + real Slack + real Claude.
