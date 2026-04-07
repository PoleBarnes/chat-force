# P4 — Channel Routing + Vibe Loop + Context Visibility + Grill-Me

**Status:** Spec, awaiting implementation
**Depends on:** P0-P2 (complete), P3 (7/9, non-blocking for P4)
**Target branch:** `pivot/agent-sdk`
**Completes:** ROADMAP P4; REQUIREMENTS.md Part 1 "Slack Integration" and "Vibe Code Loop" sections

---

## 1. Goal

After P4, each bot has four Slack channels with distinct behaviors:

- **#slug-intake** — customer-facing. Eval gate on output. Grill-me fires when harness is thin.
- **#slug-floor** — prototyping sandbox. Free-form, no eval gate. Mechanic runs after (not before).
- **#slug-mechanic-log** — engine-write-only. Structured fix proposals surface here.
- **#slug-assets** — knowledge base. Uploads ingested to `vault/raw/uploads/`.

Every bot response includes a context window usage footer (🟢/🟡/🔴).

## 2. Non-Goals (deferred past P4)

- Mechanical eval rule engine (regex/url_check/length) — v1 uses LLM-judge only
- Full vault ingest/query/lint pipelines — v1 has the directory structure + read access
- Multi-channel session handoff (start in intake, continue in floor) — future UX
- Deliverable backends other than filesystem

---

## 3. Channel Role Resolution

### 3.1 How it works

`workspace.yaml` already declares four channel IDs:

```yaml
channels:
  intake: "C01BLKINTAKE"
  factory_floor: "C01BLKFLOOR"
  mechanic_log: "C01BLKMECHLOG"
  brand_assets: "C01BLKASSETS"
```

New helper in `pipeline/slack_listener.py`:

```python
def _resolve_channel_role(channel_id: str) -> str | None:
    """Return the role ('intake', 'factory_floor', 'mechanic_log', 'brand_assets')
    for a known channel, or None for unknown channels."""
    channels = config.harness.workspace.channels
    role_map = {
        channels.intake: "intake",
        channels.factory_floor: "factory_floor",
        channels.mechanic_log: "mechanic_log",
        channels.brand_assets: "brand_assets",
    }
    return role_map.get(channel_id)
```

### 3.2 Routing in handlers

**`handle_mention` and `handle_other_messages`:**
- Resolve channel role.
- If `None` (unknown channel): ignore.
- If `mechanic_log`: ignore (engine-write-only).
- If `brand_assets`: future asset ingestion (P4 stub — log and acknowledge).
- If `intake`: run the vibe loop with eval gate.
- If `factory_floor`: run the vibe loop without eval gate.

**`handle_user_message` (assistant DMs):**
- DMs don't have a channel role — they behave like `factory_floor` (free prototyping).

---

## 4. Context Window Footer

### 4.1 Design

Every bot response appends a `ContextActionsBlock` footer showing:

```
Context: 🟢 23% | Turn 3 | $0.42
```

Thresholds:
- 🟢 under 40% — plenty of room
- 🟡 40–85% — getting full, consider closing soon
- 🔴 above 85% — close the session after this turn

### 4.2 Implementation

New `pipeline/slack_format.py`:

```python
def context_footer(usage: dict, model_context_window: int = 200_000) -> str:
    """Format context window usage as a one-line footer string."""
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    total_tokens = input_tokens + output_tokens
    cost = usage.get("total_cost_usd", 0.0)

    pct = (total_tokens / model_context_window * 100) if model_context_window > 0 else 0
    if pct < 40:
        indicator = "🟢"
    elif pct < 85:
        indicator = "🟡"
    else:
        indicator = "🔴"

    return f"Context: {indicator} {pct:.0f}% | ${cost:.2f}"
```

The footer is appended to every bot response via `say()` or `chat_stream`. Graceful fallback: if `get_usage()` fails, show "Context: unknown".

### 4.3 Where to add `model_context_window`

Add optional field to `workspace.yaml` → `BotConfig`:

```python
class BotConfig(BaseModel):
    ...
    model_context_window: PositiveInt = 200_000
```

---

## 5. Grill-Me Integration

### 5.1 When to invoke

Before starting the vibe loop in `#intake`, check harness "thinness":

```python
def _harness_is_thin(harness: LoadedHarness) -> bool:
    """Check if the harness identity/eval is too thin to produce good work."""
    identity = harness.identity
    thin_threshold = 100  # chars — a placeholder sentence

    for field in [identity.mission, identity.brand, identity.avatar]:
        if len(field.strip()) < thin_threshold:
            return True

    if not harness.eval_criteria.checks and len(harness.eval_criteria.narrative.strip()) < thin_threshold:
        return True

    return False
```

### 5.2 How to invoke

When thin, prepend the `skills/grill-me.md` content to the Worker's system prompt:

```python
grill_me_path = harness.harness_path / "skills" / "grill-me.md"
if grill_me_path.exists() and _harness_is_thin(harness):
    grill_content = grill_me_path.read_text(encoding="utf-8")
    # Prepend to the task instruction, not the system prompt
    task = f"[GRILL-ME MODE]\n\n{grill_content}\n\n---\n\nUser's request:\n{original_task}"
```

### 5.3 Session summary

After a grill session closes, the Worker should have written answers into harness identity/eval files. The session summary at `vault/summaries/sessions/<date>-grill-<topic>.md` is written by the Worker during the session (the Worker has write access to `/harness/vault/`).

---

## 6. Mechanic-Log Writer

### 6.1 After session close

In `_run_mechanic_phase`, after the Mechanic produces a verdict or proposal:

```python
mechanic_log_dir = harness.harness_path / "mechanic-log"
entry_path = mechanic_log_dir / f"{date}-{session.run_id[:8]}.md"
entry_path.write_text(proposal_markdown)
```

### 6.2 Post to `#mechanic-log` channel

After writing the file, post a notification:

```python
client.chat_postMessage(
    channel=config.harness.workspace.channels.mechanic_log,
    text=f":wrench: New mechanic-log entry: `{entry_path.name}`\n{summary[:200]}",
)
```

---

## 7. Deliverable Adapter

New `pipeline/deliverables.py`:

```python
class FilesystemDeliverable:
    def __init__(self, path: str):
        self.base = Path(path)
        self.base.mkdir(parents=True, exist_ok=True)

    def save(self, filename: str, content: str | bytes) -> Path:
        dest = self.base / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            dest.write_bytes(content)
        else:
            dest.write_text(content, encoding="utf-8")
        return dest
```

Wired from `workspace.yaml.deliverables.backend` — only "filesystem" supported in P4.

---

## 8. Test Strategy

### Unit tests (fast tier)

- `test_resolve_channel_role` — known channel → role, unknown → None
- `test_context_footer` — formatting, threshold indicators, fallback
- `test_harness_is_thin` — thin vs populated harness
- `test_filesystem_deliverable` — save text + binary files
- `test_mechanic_log_writer` — writes file + posts to channel

### Integration tests (slow tier)

- Post in `#intake` → verify eval gate behavior (Mechanic analyzes before response)
- Post in `#floor` → verify no eval gate (direct response)
- Verify context % appears on every reply
- Invoke grill-me with a deliberately thin harness

---

## 9. Execution Order

1. `pipeline/slack_format.py` — context footer helper + tests
2. Channel role resolution in `slack_listener.py` + tests
3. `pipeline/deliverables.py` — filesystem adapter + tests
4. Mechanic-log writer in `session_manager.py` + tests
5. Grill-me thinness check + invocation + tests
6. Wire all into `handle_mention` and `handle_user_message`
7. Customer feedback ingestion handler (reactions/replies)
8. Live smoke test with channel routing

---

## 10. P4 Definition of Done

1. `_resolve_channel_role()` correctly maps all four channel IDs
2. Mention in `#intake` → session with eval gate
3. Mention in `#floor` → session without eval gate
4. Message in `#mechanic-log` from user → ignored
5. Every bot response has context % footer
6. Thin harness in `#intake` → grill-me fires before the vibe loop
7. Session close → mechanic-log entry written to disk + posted to `#mechanic-log`
8. Deliverable saved to filesystem path from `workspace.yaml`
9. All fast tests pass
