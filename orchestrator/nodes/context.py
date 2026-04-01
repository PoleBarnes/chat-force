"""Three-tier context assembly for the orchestrator.

Context tiers (loaded in order, later tiers take precedence):
  1. Platform Memory  — ``platform/base-config.yaml`` (shared config, limits, models)
  2. Workspace Memory  — ``workspaces/{id}/config.yaml`` + ``context.md``
  3. Thread Memory     — Recent conversation messages (passed in from the interface)
  4. Current Input     — The user's latest message

The assembled context string is token-budget-aware: if the combined text
exceeds the budget, earlier thread messages are truncated first.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Rough estimate: 1 token ~ 4 characters for English text.
_CHARS_PER_TOKEN = 4

# Project root is three levels up from this file:
# orchestrator/nodes/context.py -> orchestrator/nodes -> orchestrator -> project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _read_file_safe(path: Path) -> str:
    """Read a file and return its contents, or empty string on failure."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.debug("Context file not found: %s", path)
        return ""
    except OSError as exc:
        logger.warning("Could not read context file %s: %s", path, exc)
        return ""


def _load_yaml_safe(path: Path) -> dict[str, Any]:
    """Load a YAML file and return a dict, or empty dict on failure."""
    text = _read_file_safe(path)
    if not text:
        return {}
    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        logger.warning("Invalid YAML in %s: %s", path, exc)
        return {}


def load_platform_config() -> dict[str, Any]:
    """Load the platform-wide base configuration.

    Returns the parsed YAML from ``platform/base-config.yaml``.
    """
    return _load_yaml_safe(_PROJECT_ROOT / "platform" / "base-config.yaml")


def load_workspace_config(workspace_id: str) -> dict[str, Any]:
    """Load the workspace-specific configuration.

    Parameters
    ----------
    workspace_id:
        Directory name under ``workspaces/``.

    Returns
    -------
    dict
        Parsed workspace config, or empty dict if not found.
    """
    return _load_yaml_safe(
        _PROJECT_ROOT / "workspaces" / workspace_id / "config.yaml"
    )


def load_workspace_context(workspace_id: str) -> str:
    """Load the workspace context markdown (brand guidelines, preferences, etc.).

    Parameters
    ----------
    workspace_id:
        Directory name under ``workspaces/``.

    Returns
    -------
    str
        The raw markdown contents of ``context.md``, or empty string.
    """
    return _read_file_safe(
        _PROJECT_ROOT / "workspaces" / workspace_id / "context.md"
    )


def _format_platform_context(config: dict[str, Any]) -> str:
    """Format platform config into a context block."""
    if not config:
        return ""
    sections = ["## Platform Configuration"]
    if "platform" in config:
        sections.append(f"- Name: {config['platform'].get('name', 'Unknown')}")
        sections.append(f"- Version: {config['platform'].get('version', '?')}")
    if "models" in config:
        models = config["models"]
        primary = models.get("primary", {})
        sections.append(f"- Complex model: {primary.get('complex', '?')}")
        sections.append(f"- Routine model: {primary.get('routine', '?')}")
    if "limits" in config:
        limits = config["limits"]
        sections.append(f"- Token budget per task: {limits.get('per_task_tokens', '?')}")
        sections.append(
            f"- Timeout: {limits.get('per_task_timeout_minutes', '?')} minutes"
        )
    return "\n".join(sections)


def _format_workspace_context(
    config: dict[str, Any], context_md: str
) -> str:
    """Format workspace config + context.md into a context block."""
    sections: list[str] = []
    if config:
        ws = config.get("workspace", {})
        sections.append("## Workspace Configuration")
        if ws.get("name"):
            sections.append(f"- Client: {ws['name']}")
        sections.append(f"- Tier: {ws.get('tier', 'standard')}")
        sops_cfg = ws.get("sops", {})
        enabled_sops = sops_cfg.get("enabled", [])
        if enabled_sops:
            sections.append(f"- Enabled SOPs: {', '.join(enabled_sops)}")
    if context_md:
        sections.append("\n## Workspace Context")
        sections.append(context_md)
    return "\n".join(sections)


def _format_thread_context(messages: list[dict[str, Any]]) -> str:
    """Format thread messages into a context block.

    Each message dict is expected to have at least ``role`` and ``content`` keys.
    """
    if not messages:
        return ""
    lines = ["## Conversation History"]
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        lines.append(f"**{role}**: {content}")
    return "\n".join(lines)


def _truncate_to_budget(
    sections: list[str], current_input: str, token_budget: int
) -> str:
    """Combine context sections and truncate to fit the token budget.

    Strategy: the current input and platform context are always kept.
    Thread messages are truncated from the oldest first if needed.
    """
    char_budget = token_budget * _CHARS_PER_TOKEN

    # sections order: [platform, workspace, thread]
    # Priority (highest to lowest): current_input > platform > workspace > thread
    input_section = f"## Current Request\n{current_input}"
    fixed_parts = [input_section]
    if sections:
        fixed_parts.insert(0, sections[0])  # platform context

    fixed_text = "\n\n---\n\n".join(fixed_parts)
    remaining_budget = char_budget - len(fixed_text)

    variable_parts: list[str] = []
    for section in sections[1:]:  # workspace, thread
        if not section:
            continue
        if remaining_budget <= 0:
            logger.info("Token budget exhausted; dropping remaining context.")
            break
        if len(section) <= remaining_budget:
            variable_parts.append(section)
            remaining_budget -= len(section)
        else:
            # Truncate this section to fit
            truncated = section[:remaining_budget]
            last_newline = truncated.rfind("\n")
            if last_newline > 0:
                truncated = truncated[:last_newline]
            variable_parts.append(truncated + "\n\n[...truncated for token budget]")
            remaining_budget = 0

    all_parts = [sections[0]] if sections else []
    all_parts.extend(variable_parts)
    all_parts.append(input_section)
    return "\n\n---\n\n".join(all_parts)


def assemble_context(
    workspace_id: str,
    thread_messages: list[dict[str, Any]],
    current_input: str,
    token_budget: int = 100_000,
) -> str:
    """Assemble full context from platform + workspace + thread + current input.

    Parameters
    ----------
    workspace_id:
        The workspace directory name (e.g. ``"acme-corp"``).
    thread_messages:
        List of prior conversation messages, each with ``role`` and ``content``.
    current_input:
        The user's latest message text.
    token_budget:
        Approximate token limit for the combined context string.

    Returns
    -------
    str
        A structured text block ready to be injected into an LLM call.
    """
    platform_config = load_platform_config()
    workspace_config = load_workspace_config(workspace_id)
    workspace_context_md = load_workspace_context(workspace_id)

    sections = [
        _format_platform_context(platform_config),
        _format_workspace_context(workspace_config, workspace_context_md),
        _format_thread_context(thread_messages),
    ]

    # Filter out empty sections
    sections = [s for s in sections if s.strip()]

    return _truncate_to_budget(sections, current_input, token_budget)
