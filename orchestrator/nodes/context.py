"""Three-tier context assembly for the orchestrator.

Context tiers (loaded in order, later tiers take precedence):
  1. Platform Memory  — ``base-config.yaml`` (shared config, limits, models)
  2. Workspace Memory  — ``docker/config/workspace/{id}/config.yaml`` + ``context.md``
  3. Thread Memory     — Recent conversation messages (passed in from the interface)
  4. Current Input     — The user's latest message

The assembled context string is token-budget-aware: if the combined text
exceeds the budget, earlier thread messages are truncated first.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from .utils import PROJECT_ROOT, load_yaml_safe, read_file_safe

logger = logging.getLogger(__name__)

# Rough estimate: 1 token ~ 4 characters for English text.
_CHARS_PER_TOKEN = 4


def load_platform_config() -> dict[str, Any]:
    """Load the platform-wide base configuration.

    Returns the parsed YAML from ``base-config.yaml``.
    """
    return load_yaml_safe(PROJECT_ROOT / "base-config.yaml")


def load_workspace_config(workspace_id: str) -> dict[str, Any]:
    """Load the workspace-specific configuration.

    Parameters
    ----------
    workspace_id:
        Directory name under ``docker/config/workspace/``.

    Returns
    -------
    dict
        Parsed workspace config, or empty dict if not found.
    """
    return load_yaml_safe(
        PROJECT_ROOT / "docker" / "config" / "workspace" / workspace_id / "config.yaml"
    )


def load_workspace_context(workspace_id: str) -> str:
    """Load the workspace context markdown (brand guidelines, preferences, etc.).

    Parameters
    ----------
    workspace_id:
        Directory name under ``docker/config/workspace/``.

    Returns
    -------
    str
        The raw markdown contents of ``context.md``, or empty string.
    """
    return read_file_safe(
        PROJECT_ROOT / "docker" / "config" / "workspace" / workspace_id / "context.md"
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


def _load_skills(skill_names: list[str] | None = None) -> str:
    """Load skill markdown files and return their content.

    If *skill_names* is provided, load only those skills.
    Otherwise, load all enabled skills from ``base-config.yaml``.

    Skill files live in ``skills/*.md`` and use YAML frontmatter to declare
    their ``name``, ``triggers``, and ``enabled_by_default`` status.
    """
    skills_dir = PROJECT_ROOT / "skills"
    if not skills_dir.is_dir():
        return ""

    # If no specific skills requested, get enabled ones from config
    if skill_names is None:
        config = load_platform_config()
        skills_config = config.get("skills", [])
        skill_names = [
            s["name"]
            for s in skills_config
            if isinstance(s, dict) and s.get("enabled_by_default", False)
        ]

    sections: list[str] = []
    for skill_file in sorted(skills_dir.glob("*.md")):
        if skill_file.name == "README.md":
            continue
        content = read_file_safe(skill_file)
        if not content:
            continue
        # Extract name from YAML frontmatter
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                frontmatter = content[3:end].strip()
                for line in frontmatter.split("\n"):
                    if line.startswith("name:"):
                        name = line.split(":", 1)[1].strip()
                        if skill_names and name not in skill_names:
                            break
                        sections.append(content[end + 3:].strip())
                        break

    if not sections:
        return ""
    return "## Available Skills\n\n" + "\n\n---\n\n".join(sections)


def _match_skills_for_task(user_input: str, matched_sop: str | None = None) -> list[str]:
    """Determine which skills are relevant to the current task.

    Strategy:
    1. If an SOP is matched, load skills referenced by that SOP's specialist
       types / agent fields.
    2. Otherwise, match skills whose ``triggers`` keywords appear in the input.
    3. Never return more than 3 skills to respect token budget.
    """
    skills_dir = PROJECT_ROOT / "skills"
    if not skills_dir.is_dir():
        return []

    # Build a map of skill name -> triggers from frontmatter
    skill_triggers: dict[str, list[str]] = {}
    for skill_file in sorted(skills_dir.glob("*.md")):
        if skill_file.name == "README.md":
            continue
        content = read_file_safe(skill_file)
        if not content or not content.startswith("---"):
            continue
        end = content.find("---", 3)
        if end <= 0:
            continue
        frontmatter = content[3:end].strip()
        name = ""
        triggers: list[str] = []
        for line in frontmatter.split("\n"):
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip()
            elif line.strip().startswith("- ") and triggers is not None:
                trigger_val = line.strip()[2:].strip()
                triggers.append(trigger_val)
        if name:
            skill_triggers[name] = triggers

    # Strategy 1: SOP-based matching
    if matched_sop:
        sop_path = PROJECT_ROOT / "sops"
        matched_skills: list[str] = []
        if sop_path.is_dir():
            for yaml_file in sop_path.glob("*.yaml"):
                try:
                    data = yaml.safe_load(read_file_safe(yaml_file))
                    if not isinstance(data, dict):
                        continue
                    sop_name = data.get("name", yaml_file.stem)
                    if sop_name.lower() != matched_sop.lower():
                        continue
                    # Collect specialist types and agent fields from SOP steps
                    sop_keywords: set[str] = set()
                    for step in data.get("steps", []):
                        specialist = step.get("specialist", "")
                        agent = step.get("agent", "")
                        desc = step.get("description", "").lower()
                        if specialist:
                            sop_keywords.add(specialist)
                        if agent:
                            sop_keywords.add(agent)
                        # Extract category-relevant words from descriptions
                        for word in ["research", "campaign", "code", "review", "briefing"]:
                            if word in desc:
                                sop_keywords.add(word)

                    # Match skills whose triggers overlap with SOP keywords
                    input_lower = user_input.lower()
                    for skill_name, triggers in skill_triggers.items():
                        for trigger in triggers:
                            if trigger.lower() in input_lower or trigger.lower() in sop_keywords:
                                if skill_name not in matched_skills:
                                    matched_skills.append(skill_name)
                                break
                        # Also check if skill name appears in SOP keywords
                        for kw in sop_keywords:
                            if kw in skill_name:
                                if skill_name not in matched_skills:
                                    matched_skills.append(skill_name)
                                break
                except (yaml.YAMLError, OSError):
                    continue
        if matched_skills:
            return matched_skills[:3]

    # Strategy 2: Keyword matching against skill triggers
    input_lower = user_input.lower()
    scored: list[tuple[str, int]] = []
    for skill_name, triggers in skill_triggers.items():
        score = 0
        for trigger in triggers:
            if trigger == "automatic":
                continue
            if trigger.lower() in input_lower:
                score += 1
        if score > 0:
            scored.append((skill_name, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [name for name, _ in scored[:3]]


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
    For thread sections (conversation history), truncation keeps the NEWEST
    messages by dropping from the start rather than the end.
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
            is_thread = section.startswith("## Conversation History")
            if is_thread:
                # For thread context, keep the NEWEST messages (truncate from start).
                # Extract the header line first, then truncate body from the start.
                header_end = section.find("\n")
                if header_end > 0:
                    header = section[:header_end]
                    body = section[header_end:]
                    budget_for_body = remaining_budget - len(header) - len("\n\n[...older messages truncated for token budget]\n")
                    if budget_for_body > 0:
                        tail = body[-budget_for_body:]
                        # Find the next message boundary (line starting with **)
                        # to avoid cutting mid-message
                        boundary = tail.find("\n**")
                        if boundary >= 0:
                            tail = tail[boundary:]
                        truncated = header + "\n\n[...older messages truncated for token budget]\n" + tail
                    else:
                        truncated = header + "\n\n[...truncated for token budget]"
                else:
                    truncated = section[-remaining_budget:]
            else:
                # For non-thread sections, truncate from the end (keep earliest content).
                truncated = section[:remaining_budget]
                last_newline = truncated.rfind("\n")
                if last_newline > 0:
                    truncated = truncated[:last_newline]
                truncated = truncated + "\n\n[...truncated for token budget]"
            variable_parts.append(truncated)
            remaining_budget = 0

    all_parts = [sections[0]] if sections else []
    all_parts.extend(variable_parts)
    all_parts.append(input_section)
    return "\n\n---\n\n".join(all_parts)


def _validate_workspace_id(workspace_id: str) -> str:
    """Validate workspace_id to prevent path traversal."""
    if not re.match(r'^[a-zA-Z0-9_-]+$', workspace_id):
        raise ValueError(
            f"Invalid workspace_id: {workspace_id!r} "
            "— must be alphanumeric with hyphens/underscores only"
        )
    return workspace_id


def assemble_context(
    workspace_id: str,
    thread_messages: list[dict[str, Any]],
    current_input: str,
    token_budget: int = 100_000,
    matched_sop: str | None = None,
    skill_names: list[str] | None = None,
) -> str:
    """Assemble full context from platform + workspace + skills + thread + current input.

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
    matched_sop:
        If a SOP was matched, its name. Used to select relevant skills.
    skill_names:
        Explicit list of skill names to load. If ``None``, skills are
        selected automatically based on the task and matched SOP.

    Returns
    -------
    str
        A structured text block ready to be injected into an LLM call.
    """
    _validate_workspace_id(workspace_id)
    platform_config = load_platform_config()
    workspace_config = load_workspace_config(workspace_id)
    workspace_context_md = load_workspace_context(workspace_id)

    # Select relevant skills based on the task
    if skill_names is None:
        relevant_skills = _match_skills_for_task(current_input, matched_sop)
    else:
        relevant_skills = skill_names

    skills_section = _load_skills(relevant_skills) if relevant_skills else ""

    sections = [
        _format_platform_context(platform_config),
        _format_workspace_context(workspace_config, workspace_context_md),
        skills_section,
        _format_thread_context(thread_messages),
    ]

    # Filter out empty sections
    sections = [s for s in sections if s.strip()]

    return _truncate_to_budget(sections, current_input, token_budget)
