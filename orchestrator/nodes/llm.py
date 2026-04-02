"""Thin wrapper around the Anthropic SDK for LLM calls.

All LLM interactions in the orchestrator go through this module so we have
a single place to manage credentials, model selection, retries, and logging.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import anthropic
import yaml

try:
    from audit.audit_logger import AuditLogger, AuditEventType
    _audit = AuditLogger(workspace_id="platform")
except Exception:
    _audit = None

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

_client: Optional[anthropic.Anthropic] = None


def get_client() -> anthropic.Anthropic:
    """Return a cached Anthropic client using env-var credentials.

    The API key is read from ``ANTHROPIC_AUTH_TOKEN`` (injected by Doppler).
    """
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_AUTH_TOKEN is not set. "
                "Ensure Doppler is configured or the env var is exported."
            )
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


# ---------------------------------------------------------------------------
# Temperature config
# ---------------------------------------------------------------------------

def get_temperature(task_type: str = "planning") -> float:
    """Get the configured temperature for a task type.

    Reads from ``base-config.yaml`` under ``models.temperature``.

    Types: creative (0.7), planning (0.0), mechanic (0.0), routine (0.0)
    """
    config_path = Path(__file__).resolve().parent.parent.parent / "base-config.yaml"
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        temps = config.get("models", {}).get("temperature", {})
        return float(temps.get(task_type, 0.0))
    except (FileNotFoundError, yaml.YAMLError, KeyError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# Text completion
# ---------------------------------------------------------------------------

def call_claude(
    prompt: str,
    system: str = "",
    model: str = "claude-opus-4-6",
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> str:
    """Call Claude and return the text response.

    Parameters
    ----------
    prompt:
        The user-turn message content.
    system:
        Optional system prompt.
    model:
        Anthropic model identifier (e.g. ``claude-opus-4-6``, ``claude-sonnet-4-6``).
    temperature:
        Sampling temperature.  Use 0.0 for deterministic planning/analysis,
        0.7 for creative tasks.
    max_tokens:
        Maximum tokens in the response.

    Returns
    -------
    str
        The text content of Claude's response.
    """
    client = get_client()
    messages = [{"role": "user", "content": prompt}]

    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }
    if system:
        kwargs["system"] = system

    try:
        response = client.messages.create(**kwargs)

        # Log the LLM call for audit trail and cost tracking
        if _audit is not None:
            try:
                _audit.log(AuditEventType.LLM_CALL, {
                    "model": model,
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "purpose": system[:100] if system else prompt[:100],
                })
            except Exception:
                logger.debug("Audit logging failed for LLM call", exc_info=True)

        # Extract text from the first content block
        for block in response.content:
            if block.type == "text":
                return block.text
        return ""
    except anthropic.APIError as exc:
        logger.error("Anthropic API error: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Structured (JSON) completion
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> dict[str, Any]:
    """Parse a JSON response, handling markdown fences gracefully."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        newline_idx = cleaned.find("\n")
        if newline_idx >= 0:
            cleaned = cleaned[newline_idx + 1:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return json.loads(cleaned.strip())


def call_claude_structured(
    prompt: str,
    system: str = "",
    response_schema: dict[str, Any] | None = None,
    model: str = "claude-opus-4-6",
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Call Claude expecting a structured JSON response via tool_use.

    Uses the Anthropic SDK's tool_use feature for reliable structured output.
    Defines a tool with the response schema, forces Claude to use it, and
    extracts the structured result from the tool_use response block.

    Parameters
    ----------
    prompt:
        The user-turn message content.
    system:
        Optional system prompt.
    response_schema:
        A JSON Schema dict describing the expected output shape.
    model:
        Anthropic model identifier.
    temperature:
        Sampling temperature.
    max_tokens:
        Maximum tokens in the response.

    Returns
    -------
    dict
        Parsed structured response.
    """
    client = get_client()

    # Define a tool that accepts the response schema
    tool_name = "structured_response"
    tools = [{
        "name": tool_name,
        "description": "Return the structured response",
        "input_schema": response_schema or {"type": "object"},
    }]

    messages = [{"role": "user", "content": prompt}]
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
        "tools": tools,
        "tool_choice": {"type": "tool", "name": tool_name},
    }
    if system:
        kwargs["system"] = system

    try:
        response = client.messages.create(**kwargs)

        # Log the LLM call for audit trail and cost tracking
        if _audit is not None:
            try:
                _audit.log(AuditEventType.LLM_CALL, {
                    "model": model,
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "purpose": f"structured: {system[:80]}" if system else f"structured: {prompt[:80]}",
                })
            except Exception:
                logger.debug("Audit logging failed for structured LLM call", exc_info=True)

        # Extract the tool_use result
        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                return block.input
        # Fallback: try to parse text response
        for block in response.content:
            if block.type == "text":
                return _parse_json_response(block.text)
        return {}
    except anthropic.APIError as exc:
        logger.error("Anthropic API error in structured call: %s", exc)
        raise
