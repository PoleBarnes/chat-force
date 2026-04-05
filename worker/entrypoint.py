import asyncio
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


WORKER_CWD = os.environ.get("WORKER_CWD", "/harness")
LATEST_RESPONSE_PATH = Path("/tmp/latest-response.txt")
NEXT_MESSAGE_PATH = Path("/tmp/next-message.txt")
TOOL_LOG_PATH = "/tmp/tool-log.jsonl"
SENTINEL_PATH = "/tmp/session-complete"
USAGE_PATH = "/tmp/usage.json"


def build_system_prompt(harness_dir: str) -> str:
    """Assemble the Worker's system prompt from the harness identity files.

    Reads /harness/identity/{mission,brand,avatar,never-list,bot-persona}.md
    (or their equivalents at harness_dir) and concatenates them under the
    section headings MISSION, BRAND, AVATAR, NEVER, PERSONA. Missing files
    are skipped silently — HarnessLoader validation already guarantees they
    exist for any production run, but tests may construct partial harnesses.
    """
    sections = []
    identity_dir = Path(harness_dir) / "identity"
    file_header_pairs = (
        ("mission.md", "MISSION"),
        ("brand.md", "BRAND"),
        ("avatar.md", "AVATAR"),
        ("never-list.md", "NEVER"),
        ("bot-persona.md", "PERSONA"),
    )

    for filename, header in file_header_pairs:
        file_path = identity_dir / filename
        if not file_path.exists():
            continue

        content = file_path.read_text(encoding="utf-8").rstrip()
        sections.append(f"# {header}\n{content}\n\n")

    return "".join(sections)


def create_pre_tool_use_hook(tool_log_path: str) -> Callable:
    async def hook(input_data, tool_use_id, context) -> dict:
        _append_jsonl(
            tool_log_path,
            {
                "event": "PreToolUse",
                "tool_name": input_data["tool_name"],
                "tool_input": input_data["tool_input"],
                "tool_use_id": input_data["tool_use_id"],
                "timestamp": _utc_timestamp(),
            },
        )
        return {"continue_": True}

    return hook


def create_post_tool_use_hook(tool_log_path: str) -> Callable:
    async def hook(input_data, tool_use_id, context) -> dict:
        _append_jsonl(
            tool_log_path,
            {
                "event": "PostToolUse",
                "tool_name": input_data["tool_name"],
                "tool_input": input_data["tool_input"],
                "tool_response": input_data["tool_response"],
                "tool_use_id": input_data["tool_use_id"],
                "timestamp": _utc_timestamp(),
            },
        )
        return {"continue_": True}

    return hook


def create_stop_hook(sentinel_path: str, usage_path: str, usage_tracker: dict) -> Callable:
    async def hook(input_data, tool_use_id, context) -> dict:
        _ensure_parent_dir(sentinel_path)
        Path(sentinel_path).touch()

        _ensure_parent_dir(usage_path)
        Path(usage_path).write_text(json.dumps(usage_tracker), encoding="utf-8")

        return {"continue_": True}

    return hook


def _append_jsonl(path: str, payload: dict) -> None:
    _ensure_parent_dir(path)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, default=str))
        handle.write("\n")


def _ensure_parent_dir(path: str) -> None:
    parent = Path(path).parent
    parent.mkdir(parents=True, exist_ok=True)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _require_env_int(name: str) -> int:
    value = os.environ.get(name)
    if value is None or value == "":
        raise RuntimeError(
            f"Required env var missing: {name} "
            f"(must be set by WorkerManager from harness limits)"
        )
    return int(value)


def _require_env_float(name: str) -> float:
    value = os.environ.get(name)
    if value is None or value == "":
        raise RuntimeError(
            f"Required env var missing: {name} "
            f"(must be set by WorkerManager from harness limits)"
        )
    return float(value)


def _ensure_git_baseline(cwd: str) -> None:
    """Initialize the worker cwd as a git repo with a baseline commit."""
    cwd_path = Path(cwd)
    git_dir = cwd_path / ".git"
    if git_dir.exists():
        return

    git_env = os.environ.copy()
    home = git_env.get("HOME")
    if not home or not Path(home).exists() or not os.access(home, os.W_OK):
        git_env["HOME"] = str(cwd_path)

    subprocess.run(["git", "init"], cwd=cwd, check=True, capture_output=True, env=git_env)
    subprocess.run(
        ["git", "config", "user.name", "worker"],
        cwd=cwd,
        check=True,
        capture_output=True,
        env=git_env,
    )
    subprocess.run(
        ["git", "config", "user.email", "worker@local"],
        cwd=cwd,
        check=True,
        capture_output=True,
        env=git_env,
    )
    subprocess.run(
        ["git", "config", "--global", "--add", "safe.directory", cwd],
        check=True,
        capture_output=True,
        env=git_env,
    )
    subprocess.run(["git", "add", "-A"], cwd=cwd, check=True, capture_output=True, env=git_env)
    subprocess.run(
        ["git", "commit", "-m", "baseline", "--allow-empty"],
        cwd=cwd,
        check=False,
        capture_output=True,
        env=git_env,
    )


def _extract_text_blocks(message) -> str:
    parts = []
    for block in getattr(message, "content", []) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def _accumulate_usage(message, usage_tracker: dict) -> None:
    usage = getattr(message, "usage", None) or {}
    usage_tracker["input_tokens"] += int(usage.get("input_tokens", 0) or 0)
    usage_tracker["output_tokens"] += int(usage.get("output_tokens", 0) or 0)


async def _run_turn(client, message_text: str, usage_tracker: dict) -> str:
    await client.query(message_text)

    assistant_text_parts = []
    final_result_text = ""

    async for message in client.receive_response():
        message_type = type(message).__name__

        if message_type == "AssistantMessage":
            _accumulate_usage(message, usage_tracker)
            assistant_text = _extract_text_blocks(message)
            if assistant_text:
                assistant_text_parts.append(assistant_text)
            continue

        if message_type == "ResultMessage":
            total_cost = getattr(message, "total_cost_usd", None)
            if total_cost is not None:
                usage_tracker["total_cost_usd"] += float(total_cost)

            result_text = getattr(message, "result", None)
            if isinstance(result_text, str) and result_text:
                final_result_text = result_text

    response_text = final_result_text or "".join(assistant_text_parts)
    LATEST_RESPONSE_PATH.write_text(response_text, encoding="utf-8")
    return response_text


def _build_client_options(
    system_prompt: str,
    usage_tracker: dict,
    ClaudeAgentOptions,
    HookMatcher,
):
    pre_hook = create_pre_tool_use_hook(TOOL_LOG_PATH)
    post_hook = create_post_tool_use_hook(TOOL_LOG_PATH)
    stop_hook = create_stop_hook(SENTINEL_PATH, USAGE_PATH, usage_tracker)

    hooks = {
        "PreToolUse": [HookMatcher(matcher=None, hooks=[pre_hook])],
        "PostToolUse": [HookMatcher(matcher=None, hooks=[post_hook])],
        "Stop": [HookMatcher(matcher=None, hooks=[stop_hook])],
    }

    options_kwargs = {
        "system_prompt": system_prompt,
        "permission_mode": "bypassPermissions",
        "max_turns": _require_env_int("MAX_TURNS"),
        "max_budget_usd": _require_env_float("MAX_BUDGET_USD"),
        "allowed_tools": (
            os.environ.get("ALLOWED_TOOLS", "").split(",")
            if os.environ.get("ALLOWED_TOOLS")
            else None
        ),
        "hooks": hooks,
        "cwd": WORKER_CWD,
    }

    if ClaudeAgentOptions is not None:
        return ClaudeAgentOptions(**options_kwargs)

    return options_kwargs


async def _main() -> None:
    from claude_agent_sdk import ClaudeSDKClient
    from claude_agent_sdk import HookMatcher

    try:
        from claude_agent_sdk import ClaudeAgentOptions
    except ImportError:
        ClaudeAgentOptions = None

    task_instruction = os.environ.get("TASK_INSTRUCTION")
    if not task_instruction:
        raise SystemExit("TASK_INSTRUCTION env var is required")

    idle_timeout = _require_env_int("IDLE_TIMEOUT")
    _ensure_git_baseline(WORKER_CWD)

    system_prompt = build_system_prompt(WORKER_CWD)
    usage_tracker = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_cost_usd": 0.0,
    }

    client_options = _build_client_options(
        system_prompt,
        usage_tracker,
        ClaudeAgentOptions,
        HookMatcher,
    )

    loop = asyncio.get_event_loop()
    last_activity = loop.time()

    async with ClaudeSDKClient(client_options) as client:
        await _run_turn(client, task_instruction, usage_tracker)
        last_activity = loop.time()

        while True:
            if NEXT_MESSAGE_PATH.exists():
                message_text = NEXT_MESSAGE_PATH.read_text(encoding="utf-8")
                NEXT_MESSAGE_PATH.unlink(missing_ok=True)
                if message_text.strip():
                    await _run_turn(client, message_text, usage_tracker)
                    last_activity = loop.time()

            if loop.time() - last_activity > idle_timeout:
                break

            await asyncio.sleep(2)


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except SystemExit:
        raise
    except BaseException as exc:
        import traceback

        error_path = Path("/tmp/worker-error.txt")
        error_path.write_text(
            f"Worker crash: {type(exc).__name__}: {exc}\n\n{traceback.format_exc()}",
            encoding="utf-8",
        )
        Path(SENTINEL_PATH).touch()
        raise
