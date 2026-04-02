"""Agent dispatch interface for SOP step execution.

Each SOP step specifies an ``agent`` field that determines which system
executes it. This module provides the dispatch logic.

Currently implemented: openclaw (Claude)
Planned: perplexity, claude_code, api:gemini, api:imagemagick, computer_use
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from .llm import call_claude, get_temperature

logger = logging.getLogger(__name__)

# Registry of available agent dispatchers
_AGENT_REGISTRY: dict[str, Callable[..., str]] = {}


def register_agent(name: str):
    """Decorator to register an agent dispatcher."""

    def decorator(fn: Callable[..., str]) -> Callable[..., str]:
        _AGENT_REGISTRY[name] = fn
        return fn

    return decorator


@register_agent("openclaw")
@register_agent("general")
def dispatch_claude(
    prompt: str, system: str = "", specialist: str = "general", **kwargs: Any
) -> str:
    """Dispatch to Claude via the Anthropic API."""
    # Determine model and temperature based on specialist
    model = "claude-sonnet-4-6"
    if specialist in ("strategist", "analyst", "developer"):
        model = "claude-opus-4-6"

    creative = specialist in ("writer", "general")
    temperature = get_temperature("creative") if creative else 0.0

    return call_claude(
        prompt=prompt,
        system=system,
        model=model,
        temperature=temperature,
    )


@register_agent("perplexity")
def dispatch_perplexity(
    prompt: str, system: str = "", **kwargs: Any
) -> str:
    """Dispatch to Perplexity for deep research.

    TODO: Implement Perplexity Computer integration via Slack @mention.
    Falls back to Claude with research-focused prompt for now.
    """
    logger.info(
        "Perplexity agent not yet connected -- falling back to Claude with research focus"
    )
    enhanced_system = (
        f"{system}\n\n"
        "IMPORTANT: You are acting as a research specialist. "
        "Cite sources with URLs. Be thorough and fact-based. "
        "Conduct multiple research passes."
    )
    return call_claude(
        prompt=prompt,
        system=enhanced_system,
        model="claude-opus-4-6",
        temperature=0.0,
    )


@register_agent("claude_code")
def dispatch_claude_code(
    prompt: str, system: str = "", **kwargs: Any
) -> str:
    """Dispatch to Claude Code for software engineering tasks.

    TODO: Implement headless Claude Code via acpx.
    Falls back to Claude with developer-focused prompt for now.
    """
    logger.info(
        "Claude Code agent not yet connected -- falling back to Claude with developer focus"
    )
    enhanced_system = (
        f"{system}\n\n"
        "IMPORTANT: You are writing production code. "
        "Include complete, working implementations. "
        "Follow best practices for the language/framework."
    )
    return call_claude(
        prompt=prompt,
        system=enhanced_system,
        model="claude-opus-4-6",
        temperature=0.0,
    )


def dispatch_api(api_name: str, prompt: str, **kwargs: Any) -> str:
    """Dispatch to an external API tool (gemini, imagemagick, etc.).

    TODO: Implement API dispatchers.
    Falls back to Claude for now.
    """
    logger.info("API agent '%s' not yet connected -- falling back to Claude", api_name)
    return call_claude(
        prompt=prompt,
        system=f"You are simulating the {api_name} API. Describe what the API would produce.",
        temperature=0.0,
    )


def dispatch(
    agent: str,
    prompt: str,
    system: str = "",
    specialist: str = "general",
    **kwargs: Any,
) -> str:
    """Dispatch a task to the appropriate agent.

    Parameters
    ----------
    agent:
        The agent identifier (e.g. ``"openclaw"``, ``"perplexity"``, ``"api:gemini"``).
    prompt:
        The task prompt.
    system:
        System instructions.
    specialist:
        The specialist type for Claude-based dispatch.
    """
    # Handle api:xxx format
    if agent.startswith("api:"):
        api_name = agent[4:]
        return dispatch_api(api_name, prompt, **kwargs)

    # Look up in registry
    dispatcher = _AGENT_REGISTRY.get(agent)
    if dispatcher:
        return dispatcher(prompt=prompt, system=system, specialist=specialist, **kwargs)

    # Fall back to Claude
    logger.warning("Unknown agent '%s' -- falling back to Claude", agent)
    return dispatch_claude(prompt=prompt, system=system, specialist=specialist, **kwargs)
