# Claude Agent SDK Python - Complete Deep Dive

**Source:** https://github.com/anthropics/claude-agent-sdk-python
**Version analyzed:** 0.1.56 (bundled CLI 2.1.92)
**Python requirement:** 3.10+
**License:** Anthropic Commercial Terms of Service

---

## Architecture Overview

The SDK is a Python wrapper around the **Claude Code CLI**. It does NOT call the
Anthropic Messages API directly. Instead it:

1. Spawns the Claude Code CLI as a subprocess (`SubprocessCLITransport`)
2. Communicates via stdin/stdout using a JSON streaming protocol (`stream-json`)
3. Handles a bidirectional **control protocol** for hooks, permissions, MCP, and agents
4. Parses CLI output into typed Python dataclasses

The CLI binary is bundled in the wheel (`_bundled/claude`) -- no separate install
required. You can override with `cli_path`.

```
Your Python Code
    |
    v
query() / ClaudeSDKClient
    |
    v
InternalClient -> SubprocessCLITransport (spawns `claude` CLI)
    |                  |
    v                  v
Query (control proto)  CLI Process (does actual API calls)
    |
    v
parse_message() -> typed Message objects
```

---

## 1. ClaudeAgentOptions - Every Parameter

All parameters with their types, defaults, and purpose:

### Core Configuration

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `system_prompt` | `str \| SystemPromptPreset \| SystemPromptFile \| None` | `None` | System prompt. `None` = empty string (vanilla Claude). String = full replacement. Preset = `{"type": "preset", "preset": "claude_code"}` uses the default Claude Code prompt. Preset with append = `{"type": "preset", "preset": "claude_code", "append": "..."}`. File = `{"type": "file", "path": "/path/to/file"}`. |
| `model` | `str \| None` | `None` | Model ID or alias. Examples: `"claude-sonnet-4-5"`, `"claude-opus-4-1-20250805"`. None = Claude Code default. |
| `fallback_model` | `str \| None` | `None` | Fallback model when primary is unavailable. |
| `cwd` | `str \| Path \| None` | `None` | Working directory for the CLI process. |
| `max_turns` | `int \| None` | `None` | Maximum number of agentic turns (tool use cycles). |
| `max_budget_usd` | `float \| None` | `None` | Maximum cost in USD. Checked after each API call completes -- may slightly overshoot. ResultMessage.subtype = `"error_max_budget_usd"` when exceeded. |
| `task_budget` | `TaskBudget \| None` | `None` | API-side token budget. `{"total": 50000}`. The model is made aware of remaining budget and can pace itself. Uses `task-budgets-2026-03-13` beta header. |

### Tool Configuration

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `tools` | `list[str] \| ToolsPreset \| None` | `None` | **Base tool set**. `None` = all default Claude Code tools. `["Read", "Bash"]` = only these tools available. `[]` = no tools. `{"type": "preset", "preset": "claude_code"}` = all defaults. |
| `allowed_tools` | `list[str]` | `[]` | **Permission allowlist** -- auto-approve these tools (no permission prompt). Does NOT add tools. Unlisted tools fall through to `permission_mode` or `can_use_tool`. For MCP tools: `"mcp__<server>__<tool>"`. |
| `disallowed_tools` | `list[str]` | `[]` | **Blocklist** -- completely block these tools. |

### Permission System

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `permission_mode` | `PermissionMode \| None` | `None` | `"default"` = CLI prompts for dangerous tools. `"acceptEdits"` = auto-accept file edits. `"plan"` = plan only, no tool execution. `"bypassPermissions"` = allow all tools. `"dontAsk"` = allow all without prompting. |
| `can_use_tool` | `CanUseTool \| None` | `None` | Python callback for programmatic permission decisions. Signature: `async (tool_name: str, input_data: dict, context: ToolPermissionContext) -> PermissionResultAllow \| PermissionResultDeny`. **Requires ClaudeSDKClient** (streaming mode). Cannot be used with `permission_prompt_tool_name`. |
| `permission_prompt_tool_name` | `str \| None` | `None` | Low-level: tool name for permission prompts. Auto-set to `"stdio"` when `can_use_tool` is provided. |

### MCP Server Configuration

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `mcp_servers` | `dict[str, McpServerConfig] \| str \| Path` | `{}` | MCP servers. Dict maps name to config. String/Path = file path or JSON string for `--mcp-config`. |

McpServerConfig variants:
- **stdio**: `{"command": "python", "args": ["-m", "server"], "env": {"KEY": "val"}}` -- type field optional
- **sse**: `{"type": "sse", "url": "http://...", "headers": {...}}`
- **http**: `{"type": "http", "url": "http://...", "headers": {...}}`
- **sdk**: `{"type": "sdk", "name": "...", "instance": <McpServer>}` -- in-process, created via `create_sdk_mcp_server()`

### Session Management

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `continue_conversation` | `bool` | `False` | Continue the most recent conversation (`--continue`). |
| `resume` | `str \| None` | `None` | Resume a specific session by ID (`--resume <id>`). |
| `session_id` | `str \| None` | `None` | Specify a custom session ID (`--session-id <id>`). |
| `fork_session` | `bool` | `False` | When resuming, fork to a new session ID instead of continuing the previous one. |

### Agent Configuration

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `agents` | `dict[str, AgentDefinition] \| None` | `None` | Custom subagent definitions. Sent via initialize request (no CLI arg size limits). |
| `setting_sources` | `list[SettingSource] \| None` | `None` | Which settings to load: `"user"`, `"project"`, `"local"`. `None` = SDK default (no settings loaded = isolated). Must be explicitly set to load CLAUDE.md, agents, slash commands, etc. |

### Hook Configuration

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `hooks` | `dict[HookEvent, list[HookMatcher]] \| None` | `None` | Python hook callbacks. **Requires ClaudeSDKClient**. Keys are event names, values are lists of `HookMatcher` objects. |

### Thinking/Reasoning

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `thinking` | `ThinkingConfig \| None` | `None` | Controls extended thinking. `{"type": "adaptive"}` = adaptive (default 32k tokens). `{"type": "enabled", "budget_tokens": N}` = fixed budget. `{"type": "disabled"}` = off. Takes precedence over `max_thinking_tokens`. |
| `max_thinking_tokens` | `int \| None` | `None` | **Deprecated.** Use `thinking` instead. |
| `effort` | `Literal["low", "medium", "high", "max"] \| None` | `None` | Thinking effort level. |

### Output Configuration

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `output_format` | `dict[str, Any] \| None` | `None` | Structured output. `{"type": "json_schema", "schema": {...}}`. The schema is passed to `--json-schema`. Result appears in `ResultMessage.structured_output`. |
| `include_partial_messages` | `bool` | `False` | Enable streaming of partial messages (StreamEvent objects interspersed with regular messages). For real-time UIs showing text as it generates. |

### Sandbox / Security

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `sandbox` | `SandboxSettings \| None` | `None` | Bash command sandboxing (macOS/Linux). Merged into settings JSON. See SandboxSettings below. |
| `settings` | `str \| None` | `None` | Settings file path or JSON string for `--settings`. If both `settings` and `sandbox` are provided, they are merged. |

SandboxSettings fields (all optional):
- `enabled: bool` -- Enable sandboxing
- `autoAllowBashIfSandboxed: bool` -- Auto-approve bash when sandboxed (default True)
- `excludedCommands: list[str]` -- Commands that bypass sandbox (e.g., `["git", "docker"]`)
- `allowUnsandboxedCommands: bool` -- Allow `dangerouslyDisableSandbox` (default True)
- `network: SandboxNetworkConfig` -- Network config (allowUnixSockets, allowLocalBinding, httpProxyPort, socksProxyPort)
- `ignoreViolations: SandboxIgnoreViolations` -- File/network paths to ignore
- `enableWeakerNestedSandbox: bool` -- For unprivileged Docker (Linux only)

### Plugin Configuration

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `plugins` | `list[SdkPluginConfig]` | `[]` | Plugin directories. Each: `{"type": "local", "path": "/path/to/plugin"}`. Plugins can provide commands, agents, skills, hooks. |

### Beta Features

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `betas` | `list[SdkBeta]` | `[]` | Beta feature flags. Currently: `"context-1m-2025-08-07"`. |

### Transport / Process Configuration

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `cli_path` | `str \| Path \| None` | `None` | Path to Claude Code CLI binary. None = auto-discover (bundled first, then PATH). |
| `env` | `dict[str, str]` | `{}` | Extra environment variables for the CLI process. |
| `extra_args` | `dict[str, str \| None]` | `{}` | Arbitrary CLI flags. `{"debug-to-stderr": None}` = `--debug-to-stderr` (boolean flag). `{"some-flag": "value"}` = `--some-flag value`. |
| `max_buffer_size` | `int \| None` | `None` | Max bytes when buffering CLI stdout. Default 1MB. |
| `stderr` | `Callable[[str], None] \| None` | `None` | Callback for each line of stderr output from CLI. |
| `debug_stderr` | `Any` | `sys.stderr` | **Deprecated.** File-like object for debug output. Use `stderr` callback instead. |
| `user` | `str \| None` | `None` | OS user to run the subprocess as (passed to `anyio.open_process`). |
| `add_dirs` | `list[str \| Path]` | `[]` | Additional directories to add (`--add-dir`). |
| `enable_file_checkpointing` | `bool` | `False` | Track file changes for rewind support. Sets `CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING=true`. Use with `rewind_files()`. |

---

## 2. Message Types in the Event Stream

`query()` and `ClaudeSDKClient.receive_messages()` yield these types:

### Message (Union type)

```python
Message = UserMessage | AssistantMessage | SystemMessage | ResultMessage | StreamEvent | RateLimitEvent
```

### UserMessage

```python
@dataclass
class UserMessage:
    content: str | list[ContentBlock]  # Text or structured blocks
    uuid: str | None = None            # Message UUID (with replay-user-messages)
    parent_tool_use_id: str | None     # Set when this is a tool result
    tool_use_result: dict | None       # Raw tool result data
```

### AssistantMessage

```python
@dataclass
class AssistantMessage:
    content: list[ContentBlock]              # TextBlock, ThinkingBlock, ToolUseBlock, ToolResultBlock
    model: str                               # Model that generated this (e.g. "claude-sonnet-4-5-20250929")
    parent_tool_use_id: str | None = None    # Set for subagent responses
    error: AssistantMessageError | None       # "authentication_failed" | "billing_error" | "rate_limit" | "invalid_request" | "server_error" | "unknown"
    usage: dict | None = None                # Per-turn usage: {"input_tokens": N, "output_tokens": N}
    message_id: str | None = None            # Anthropic API message ID
    stop_reason: str | None = None           # Why this turn ended
    session_id: str | None = None            # Session ID
    uuid: str | None = None                  # Message UUID
```

### SystemMessage

```python
@dataclass
class SystemMessage:
    subtype: str        # "init", "tool_use", "rate_limit_warning", etc.
    data: dict          # Raw payload from CLI
```

Specialized subtypes (all inherit from SystemMessage):

```python
@dataclass
class TaskStartedMessage(SystemMessage):
    task_id: str
    description: str
    uuid: str
    session_id: str
    tool_use_id: str | None = None
    task_type: str | None = None

@dataclass
class TaskProgressMessage(SystemMessage):
    task_id: str
    description: str
    usage: TaskUsage    # {total_tokens, tool_uses, duration_ms}
    uuid: str
    session_id: str
    tool_use_id: str | None = None
    last_tool_name: str | None = None

@dataclass
class TaskNotificationMessage(SystemMessage):
    task_id: str
    status: TaskNotificationStatus  # "completed" | "failed" | "stopped"
    output_file: str
    summary: str
    uuid: str
    session_id: str
    tool_use_id: str | None = None
    usage: TaskUsage | None = None
```

### ResultMessage (carries cost/usage data)

```python
@dataclass
class ResultMessage:
    subtype: str                    # "success", "error", "error_max_budget_usd", etc.
    duration_ms: int                # Total wall-clock time
    duration_api_ms: int            # Time spent in API calls
    is_error: bool                  # Whether the query errored
    num_turns: int                  # Number of agentic turns
    session_id: str                 # Session ID
    stop_reason: str | None         # Why conversation ended
    total_cost_usd: float | None    # TOTAL COST for this query
    usage: dict | None              # Aggregate usage stats
    result: str | None              # Final text result
    structured_output: Any          # Parsed JSON if output_format was set
    model_usage: dict | None        # Per-model usage breakdown
    permission_denials: list | None # Tools that were denied
    errors: list[str] | None       # Error messages if any
    uuid: str | None                # Message UUID
```

### StreamEvent (partial streaming)

```python
@dataclass
class StreamEvent:
    uuid: str
    session_id: str
    event: dict         # Raw Anthropic API stream event (content_block_delta, etc.)
    parent_tool_use_id: str | None = None
```

Only emitted when `include_partial_messages=True`.

### RateLimitEvent

```python
@dataclass
class RateLimitEvent:
    rate_limit_info: RateLimitInfo
    uuid: str
    session_id: str

@dataclass
class RateLimitInfo:
    status: RateLimitStatus          # "allowed" | "allowed_warning" | "rejected"
    resets_at: int | None            # Unix timestamp
    rate_limit_type: RateLimitType | None  # "five_hour" | "seven_day" | "seven_day_opus" | "seven_day_sonnet" | "overage"
    utilization: float | None        # 0.0 - 1.0
    overage_status: RateLimitStatus | None
    overage_resets_at: int | None
    overage_disabled_reason: str | None
    raw: dict                        # Full raw dict
```

### ContentBlock types

```python
@dataclass
class TextBlock:
    text: str

@dataclass
class ThinkingBlock:
    thinking: str
    signature: str

@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict

@dataclass
class ToolResultBlock:
    tool_use_id: str
    content: str | list[dict] | None = None
    is_error: bool | None = None
```

---

## 3. Hooks System - Complete Reference

Hooks are Python callbacks that the Claude Code **application** (not Claude the model)
invokes at specific points in the agent loop. They provide deterministic processing
and automated feedback.

**Requirement:** Hooks only work with `ClaudeSDKClient` (streaming mode).

### Hook Events

| Event | When It Fires | Matcher Matches On |
|-------|--------------|-------------------|
| `PreToolUse` | Before a tool executes | Tool name (e.g. `"Bash"`, `"Write\|Edit"`) |
| `PostToolUse` | After a tool executes successfully | Tool name |
| `PostToolUseFailure` | After a tool execution fails | Tool name |
| `UserPromptSubmit` | When user submits a prompt | N/A (use `None`) |
| `Stop` | When the main agent is about to stop | N/A |
| `SubagentStop` | When a subagent is about to stop | N/A |
| `PreCompact` | Before context compaction | N/A |
| `Notification` | When CLI sends a notification | N/A |
| `SubagentStart` | When a subagent starts | N/A |
| `PermissionRequest` | When a tool requests permission | Tool name |

### HookMatcher

```python
@dataclass
class HookMatcher:
    matcher: str | None = None     # Tool name pattern (e.g. "Bash", "Write|MultiEdit|Edit")
    hooks: list[HookCallback] = [] # List of async callback functions
    timeout: float | None = None   # Timeout in seconds (default 60)
```

### HookCallback Signature

```python
async def my_hook(
    input_data: HookInput,        # Strongly-typed dict (varies by event)
    tool_use_id: str | None,      # Tool use ID (if applicable)
    context: HookContext,         # {"signal": None} (future abort signal)
) -> HookJSONOutput:
    ...
```

### Hook Input Types

**BaseHookInput** (common fields):
- `session_id: str`
- `transcript_path: str`
- `cwd: str`
- `permission_mode: str` (optional)

**PreToolUseHookInput** extends BaseHookInput:
- `hook_event_name: "PreToolUse"`
- `tool_name: str`
- `tool_input: dict`
- `tool_use_id: str`
- `agent_id: str` (optional, present inside subagents)
- `agent_type: str` (optional)

**PostToolUseHookInput** extends BaseHookInput:
- `hook_event_name: "PostToolUse"`
- `tool_name: str`
- `tool_input: dict`
- `tool_response: Any`
- `tool_use_id: str`
- `agent_id: str` (optional)
- `agent_type: str` (optional)

**PostToolUseFailureHookInput** extends BaseHookInput:
- `hook_event_name: "PostToolUseFailure"`
- `tool_name: str`
- `tool_input: dict`
- `tool_use_id: str`
- `error: str`
- `is_interrupt: bool` (optional)
- `agent_id: str` (optional)
- `agent_type: str` (optional)

**UserPromptSubmitHookInput**: `prompt: str`

**StopHookInput**: `stop_hook_active: bool`

**SubagentStopHookInput**: `stop_hook_active: bool`, `agent_id: str`, `agent_transcript_path: str`, `agent_type: str`

**PreCompactHookInput**: `trigger: "manual" | "auto"`, `custom_instructions: str | None`

**NotificationHookInput**: `message: str`, `title: str` (optional), `notification_type: str`

**SubagentStartHookInput**: `agent_id: str`, `agent_type: str`

**PermissionRequestHookInput**: `tool_name: str`, `tool_input: dict`, `permission_suggestions: list` (optional), `agent_id: str` (optional), `agent_type: str` (optional)

### Hook Output Types

**SyncHookJSONOutput** (most common):
```python
{
    # Control fields
    "continue_": True,          # False = stop execution (converted to "continue" for CLI)
    "suppressOutput": False,    # Hide stdout from transcript
    "stopReason": "...",        # Message shown when continue_ is False

    # Decision fields
    "decision": "block",        # Block behavior
    "systemMessage": "...",     # Warning displayed to user
    "reason": "...",            # Feedback message for Claude

    # Hook-specific output
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow" | "deny" | "ask",
        "permissionDecisionReason": "...",
        "updatedInput": {...},           # Modify tool input
        "additionalContext": "...",      # Extra context for Claude
    }
}
```

**AsyncHookJSONOutput** (defer execution):
```python
{
    "async_": True,             # Defer hook execution (converted to "async" for CLI)
    "asyncTimeout": 30000,      # Timeout in milliseconds
}
```

### Hook-Specific Output Variants

| Event | hookEventName | Key Fields |
|-------|--------------|------------|
| PreToolUse | `"PreToolUse"` | `permissionDecision`, `permissionDecisionReason`, `updatedInput`, `additionalContext` |
| PostToolUse | `"PostToolUse"` | `additionalContext`, `updatedMCPToolOutput` |
| PostToolUseFailure | `"PostToolUseFailure"` | `additionalContext` |
| UserPromptSubmit | `"UserPromptSubmit"` | `additionalContext` |
| SessionStart | `"SessionStart"` | `additionalContext` |
| Notification | `"Notification"` | (no extra fields) |
| SubagentStart | `"SubagentStart"` | `additionalContext` |
| PermissionRequest | `"PermissionRequest"` | `decision: dict` |

---

## 4. Subagent / Agent Support

### Defining Agents

```python
@dataclass
class AgentDefinition:
    description: str                                     # What the agent does
    prompt: str                                          # System prompt for the agent
    tools: list[str] | None = None                       # Available tools (e.g. ["Read", "Grep"])
    disallowedTools: list[str] | None = None             # Blocked tools
    model: str | None = None                             # "sonnet", "opus", "haiku", "inherit", or full model ID
    skills: list[str] | None = None                      # Skills available to agent
    memory: Literal["user", "project", "local"] | None   # Memory scope
    mcpServers: list[str | dict] | None = None           # MCP servers (name or inline config)
    initialPrompt: str | None = None                     # Auto-sent first prompt
    maxTurns: int | None = None                          # Max turns for this agent
    background: bool | None = None                       # Run in background
    effort: Literal["low", "medium", "high", "max"] | int | None  # Thinking effort
    permissionMode: PermissionMode | None = None         # Permission mode for this agent
```

### How It Works

1. Agents are defined in `ClaudeAgentOptions.agents` as a dict of name -> AgentDefinition
2. They are sent to the CLI via the **initialize** control request (stdin), not CLI args
3. This means there is NO size limit -- you can send 260KB+ of agent definitions
4. Claude can invoke agents using the built-in `Agent` tool
5. Each agent runs as a **Task** with its own tool set, prompt, and model
6. Task progress is reported via `TaskStartedMessage`, `TaskProgressMessage`, `TaskNotificationMessage`

### Filesystem-Based Agents

Agents can also be defined as markdown files in `.claude/agents/`:

```markdown
---
name: my-agent
description: Does something useful
tools: Read, Grep
---

# Agent Prompt

You are my custom agent...
```

Load them with `setting_sources=["project"]`.

### Agent Hooks

- `SubagentStart` fires when a subagent begins (with `agent_id` and `agent_type`)
- `SubagentStop` fires when a subagent ends
- Tool-lifecycle hooks (`PreToolUse`, `PostToolUse`, `PostToolUseFailure`) include `agent_id` and `agent_type` when firing from inside a subagent

### Stopping Tasks

```python
await client.stop_task(task_id)  # task_id from TaskNotificationMessage
```

---

## 5. MCP Server Support

### External MCP Servers (subprocess)

```python
options = ClaudeAgentOptions(
    mcp_servers={
        "my-server": {
            "type": "stdio",            # Optional (default)
            "command": "python",
            "args": ["-m", "my_server"],
            "env": {"API_KEY": "..."},
        },
        "remote-server": {
            "type": "sse",
            "url": "http://localhost:8080/sse",
            "headers": {"Authorization": "Bearer ..."},
        },
        "http-server": {
            "type": "http",
            "url": "http://localhost:8080",
            "headers": {"Authorization": "Bearer ..."},
        },
    }
)
```

### In-Process SDK MCP Servers

```python
from claude_agent_sdk import tool, create_sdk_mcp_server

@tool("my_tool", "Description", {"param": str})
async def my_tool(args):
    return {"content": [{"type": "text", "text": f"Result: {args['param']}"}]}

server = create_sdk_mcp_server(name="my-server", version="1.0.0", tools=[my_tool])

options = ClaudeAgentOptions(
    mcp_servers={"tools": server},
    allowed_tools=["mcp__tools__my_tool"],  # Auto-approve
)
```

Benefits of SDK MCP servers:
- No subprocess management
- No IPC overhead
- Single process deployment
- Direct access to application state
- Same-process debugging

### Tool Input Schema Options

The `@tool` decorator accepts:
- Dict of `{name: type}`: `{"a": float, "b": float}`
- TypedDict class for complex schemas
- Full JSON Schema dict: `{"type": "object", "properties": {...}}`
- `Annotated[type, "description"]` for per-parameter descriptions

### Runtime MCP Management

```python
async with ClaudeSDKClient(options) as client:
    # Get status of all MCP servers
    status = await client.get_mcp_status()
    # Returns: {"mcpServers": [{"name": "...", "status": "connected"|"failed"|"pending"|"needs-auth"|"disabled", ...}]}

    # Reconnect a failed server
    await client.reconnect_mcp_server("my-server")

    # Disable/enable a server
    await client.toggle_mcp_server("my-server", enabled=False)
    await client.toggle_mcp_server("my-server", enabled=True)
```

### MCP Server Configuration via File

```python
options = ClaudeAgentOptions(
    mcp_servers="/path/to/mcp-config.json"  # or JSON string
)
```

File format: `{"mcpServers": {"name": {...config...}}}`

---

## 6. Memory Support

The SDK does NOT have a built-in memory tool in the Python package itself. Memory
in Claude Code works through CLAUDE.md files:

- `~/.claude/CLAUDE.md` -- user-level memory
- `.claude/CLAUDE.md` -- project-level memory
- `.claude-local/CLAUDE.md` -- local (gitignored) memory

These are loaded automatically when `setting_sources` includes the relevant scope.

**IMPORTANT:** By default, `setting_sources` is `None`, which means NO settings
(including CLAUDE.md) are loaded. To load memory files, set:

```python
options = ClaudeAgentOptions(
    setting_sources=["user", "project", "local"],
)
```

For agents, the `memory` field controls which scope they can access:

```python
AgentDefinition(
    ...,
    memory="project",  # "user", "project", or "local"
)
```

---

## 7. Computer Use Support

Computer use is NOT directly exposed in the Python SDK. The SDK wraps the Claude
Code CLI, which primarily provides developer tools (Read, Write, Edit, Bash, Grep,
Glob, etc.).

The standard tools available are:
- **Read** - Read files
- **Write** - Write files
- **Edit/MultiEdit** - Edit files
- **Bash** - Run shell commands
- **Grep** - Search file contents
- **Glob** - Find files by pattern
- **WebFetch** - Fetch web content
- **WebSearch** - Search the web
- **Agent** - Invoke subagents
- **TodoWrite** - Manage todo lists
- **NotebookEdit** - Edit Jupyter notebooks
- **EnterWorktree/ExitWorktree** - Git worktree isolation

For computer use (screenshot, mouse, keyboard), you would need to use the
Anthropic Messages API directly with the computer-use beta, not the Agent SDK.

---

## 8. Permission System - Complete Reference

### Evaluation Order

When Claude wants to use a tool, the permission system evaluates in this order:

1. `disallowed_tools` -- if the tool is listed, it is blocked (never reaches Claude)
2. `allowed_tools` -- if the tool is listed, it is auto-approved
3. `can_use_tool` callback -- if provided, called for a programmatic decision
4. `permission_mode` -- fallback mode

### Permission Modes

| Mode | Behavior |
|------|----------|
| `"default"` | CLI prompts user for dangerous tools |
| `"acceptEdits"` | Auto-accept file edits (Write, Edit, MultiEdit) |
| `"plan"` | Plan only -- no tool execution |
| `"bypassPermissions"` | Allow all tools without prompting |
| `"dontAsk"` | Allow all tools without prompting |

### can_use_tool Callback

```python
async def my_callback(
    tool_name: str,
    input_data: dict,
    context: ToolPermissionContext,
) -> PermissionResultAllow | PermissionResultDeny:
    ...

# ToolPermissionContext fields:
#   signal: None (future abort signal)
#   suggestions: list[PermissionUpdate]  -- CLI's suggested permission rules
#   tool_use_id: str | None              -- unique ID for this tool call
#   agent_id: str | None                 -- subagent ID if applicable
```

### PermissionResult types

**PermissionResultAllow:**
```python
PermissionResultAllow(
    behavior="allow",
    updated_input={"command": "safe-command"},  # Modify tool input
    updated_permissions=[                        # Update permission rules
        PermissionUpdate(
            type="addRules",
            rules=[PermissionRuleValue(tool_name="Bash", rule_content="echo *")],
            behavior="allow",
            destination="session",
        )
    ],
)
```

**PermissionResultDeny:**
```python
PermissionResultDeny(
    behavior="deny",
    message="Not allowed for security reasons",
    interrupt=False,  # True = stop the entire conversation
)
```

### Dynamic Permission Changes

```python
async with ClaudeSDKClient(options) as client:
    await client.set_permission_mode("acceptEdits")  # Change mid-conversation
```

### PermissionUpdate types

```python
PermissionUpdate(
    type="addRules" | "replaceRules" | "removeRules" | "setMode" | "addDirectories" | "removeDirectories",
    rules=[PermissionRuleValue(tool_name="Bash", rule_content="echo *")],
    behavior="allow" | "deny" | "ask",
    mode="default" | "acceptEdits" | ...,
    directories=["/path/to/dir"],
    destination="userSettings" | "projectSettings" | "localSettings" | "session",
)
```

---

## 9. Session Management

### Session Resumption

```python
# Continue the most recent session
options = ClaudeAgentOptions(continue_conversation=True)

# Resume a specific session
options = ClaudeAgentOptions(resume="550e8400-e29b-41d4-a716-446655440000")

# Resume but fork to a new session
options = ClaudeAgentOptions(
    resume="550e8400-e29b-41d4-a716-446655440000",
    fork_session=True,
)

# Specify a custom session ID
options = ClaudeAgentOptions(session_id="my-custom-session-id")
```

### Listing Sessions

```python
from claude_agent_sdk import list_sessions, get_session_info, get_session_messages

# List all sessions for a project
sessions = list_sessions(directory="/path/to/project")
# Returns: list[SDKSessionInfo] sorted by last_modified descending

# List all sessions across all projects
all_sessions = list_sessions()

# Paginate
page1 = list_sessions(limit=50)
page2 = list_sessions(limit=50, offset=50)

# Without git worktree scanning
sessions = list_sessions(directory="/path", include_worktrees=False)

# Get info for a single session
info = get_session_info("session-uuid", directory="/path/to/project")
# Returns SDKSessionInfo or None
```

**SDKSessionInfo fields:**
- `session_id: str`
- `summary: str` -- custom title, AI title, or first prompt
- `last_modified: int` -- epoch ms
- `file_size: int | None`
- `custom_title: str | None`
- `first_prompt: str | None`
- `git_branch: str | None`
- `cwd: str | None`
- `tag: str | None`
- `created_at: int | None` -- epoch ms

### Reading Session Messages

```python
messages = get_session_messages(
    "session-uuid",
    directory="/path/to/project",
    limit=10,
    offset=0,
)
# Returns: list[SessionMessage] in chronological order

# SessionMessage fields:
#   type: "user" | "assistant"
#   uuid: str
#   session_id: str
#   message: dict  (raw Anthropic API message)
#   parent_tool_use_id: None
```

### Session Mutations

```python
from claude_agent_sdk import rename_session, tag_session, delete_session, fork_session

# Rename
rename_session("session-uuid", "My Session Title", directory="/path")

# Tag
tag_session("session-uuid", "experiment-1", directory="/path")
tag_session("session-uuid", None)  # Clear tag

# Delete (permanent!)
delete_session("session-uuid", directory="/path")

# Fork
result = fork_session("session-uuid", directory="/path")
print(result.session_id)  # New forked session UUID

# Fork from a specific message
result = fork_session(
    "session-uuid",
    up_to_message_id="message-uuid",
    title="My Fork",
)
```

### Session Storage

Sessions are stored as JSONL files at:
`~/.claude/projects/<sanitized-cwd>/<session-uuid>.jsonl`

The `CLAUDE_CONFIG_DIR` env var overrides `~/.claude`.

### File Checkpointing and Rewind

```python
options = ClaudeAgentOptions(
    enable_file_checkpointing=True,
    extra_args={"replay-user-messages": None},  # Get UserMessage with uuid
)

async with ClaudeSDKClient(options) as client:
    await client.query("Make some changes")
    async for msg in client.receive_response():
        if isinstance(msg, UserMessage) and msg.uuid:
            checkpoint_id = msg.uuid

    # Later, rewind files to that checkpoint
    await client.rewind_files(checkpoint_id)
```

---

## 10. ClaudeSDKClient - Complete Method Reference

### Lifecycle

```python
# Context manager (recommended)
async with ClaudeSDKClient(options) as client:
    ...

# Manual lifecycle
client = ClaudeSDKClient(options)
await client.connect()          # or connect(prompt="...")
...
await client.disconnect()
```

### Sending Messages

```python
await client.query("Hello")                    # String prompt
await client.query(async_iterable)             # Async iterable of message dicts
await client.query("Hello", session_id="s1")   # With session ID
```

### Receiving Messages

```python
# Receive until ResultMessage (auto-terminates)
async for msg in client.receive_response():
    ...

# Receive ALL messages indefinitely (must break manually)
async for msg in client.receive_messages():
    if isinstance(msg, ResultMessage):
        break
```

### Control Operations

```python
await client.interrupt()                        # Send interrupt signal
await client.set_permission_mode("acceptEdits") # Change permissions
await client.set_model("claude-sonnet-4-5")     # Change model
await client.set_model(None)                    # Reset to default model
await client.rewind_files(user_message_id)      # Rewind file state
await client.stop_task(task_id)                 # Stop a background task
```

### MCP Management

```python
status = await client.get_mcp_status()                      # Get all server statuses
await client.reconnect_mcp_server("server-name")            # Reconnect failed server
await client.toggle_mcp_server("server-name", enabled=True) # Enable/disable
```

### Introspection

```python
usage = await client.get_context_usage()   # Context window breakdown
info = await client.get_server_info()      # Server init info (commands, output styles)
```

---

## 11. Error Types

```python
ClaudeSDKError              # Base exception
  CLIConnectionError        # Connection issues
    CLINotFoundError        # CLI binary not found
  ProcessError              # CLI process failed (has exit_code, stderr)
  CLIJSONDecodeError        # JSON parsing failed (has line, original_error)
  MessageParseError         # Message parsing failed (has data)
```

---

## 12. Transport Layer

The `Transport` abstract class can be subclassed for custom transport
implementations (e.g., remote Claude Code connections):

```python
class Transport(ABC):
    async def connect(self) -> None: ...
    async def write(self, data: str) -> None: ...
    def read_messages(self) -> AsyncIterator[dict]: ...
    async def close(self) -> None: ...
    def is_ready(self) -> bool: ...
    async def end_input(self) -> None: ...
```

Pass custom transport to `query()` or `ClaudeSDKClient`:

```python
async for msg in query(prompt="Hi", transport=my_transport):
    ...

client = ClaudeSDKClient(transport=my_transport)
```

**Warning:** The Transport API is internal and may change without notice.

---

## 13. Key Patterns for Our Use Case (Leo Agent)

### Headless Agent with Full Permissions

```python
options = ClaudeAgentOptions(
    system_prompt="You are Leo, a digital worker agent...",
    permission_mode="bypassPermissions",
    cwd="/workspace",
    setting_sources=["user", "project"],
    model="claude-sonnet-4-5",
)
```

### Agent with Programmatic Permission Control

```python
async def leo_permissions(tool_name, input_data, context):
    if tool_name == "Bash" and "rm -rf" in input_data.get("command", ""):
        return PermissionResultDeny(message="Destructive command blocked")
    return PermissionResultAllow()

options = ClaudeAgentOptions(
    can_use_tool=leo_permissions,
    cwd="/workspace",
)

async with ClaudeSDKClient(options) as client:
    await client.query("Do the task")
    async for msg in client.receive_response():
        ...
```

### Agent with Hooks for Logging

```python
async def log_all_tools(input_data, tool_use_id, context):
    print(f"Tool: {input_data['tool_name']} Input: {input_data['tool_input']}")
    return {}

options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [HookMatcher(hooks=[log_all_tools])],
        "PostToolUse": [HookMatcher(hooks=[log_all_tools])],
    },
    permission_mode="bypassPermissions",
)
```

### Multi-Agent Orchestration

```python
options = ClaudeAgentOptions(
    agents={
        "researcher": AgentDefinition(
            description="Researches codebase",
            prompt="You analyze code structure and patterns",
            tools=["Read", "Grep", "Glob"],
            model="sonnet",
        ),
        "implementer": AgentDefinition(
            description="Implements code changes",
            prompt="You write clean, tested code",
            tools=["Read", "Write", "Edit", "Bash"],
            model="sonnet",
        ),
    },
)
```

### Cost-Controlled Execution

```python
options = ClaudeAgentOptions(
    max_budget_usd=0.50,
    max_turns=10,
    task_budget={"total": 100000},
)
```

### Structured Output

```python
schema = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["success", "failure"]},
        "summary": {"type": "string"},
    },
    "required": ["status", "summary"],
}

options = ClaudeAgentOptions(
    output_format={"type": "json_schema", "schema": schema},
)

async for msg in query(prompt="Analyze this", options=options):
    if isinstance(msg, ResultMessage):
        result = msg.structured_output  # Parsed JSON matching schema
```
