"""Thin wrapper around the Anthropic SDK for LLM calls.

All LLM interactions in the orchestrator go through this module so we have
a single place to manage credentials, model selection, retries, and logging.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

import anthropic

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

def call_claude_structured(
    prompt: str,
    system: str = "",
    response_schema: Optional[Dict[str, Any]] = None,
    model: str = "claude-opus-4-6",
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Call Claude expecting a structured JSON response.

    The function instructs Claude to return valid JSON matching the optional
    *response_schema*.  The raw text is parsed with ``json.loads``; if parsing
    fails after a retry the error is raised.

    Parameters
    ----------
    prompt:
        The user-turn message content.
    system:
        Optional system prompt (schema instructions are appended automatically).
    response_schema:
        A JSON Schema dict describing the expected output shape.  Included in
        the system prompt so Claude knows what to produce.
    model:
        Anthropic model identifier.
    temperature:
        Sampling temperature.
    max_tokens:
        Maximum tokens in the response.

    Returns
    -------
    dict
        Parsed JSON response.
    """
    schema_instruction = (
        "You MUST respond with valid JSON only. No markdown, no explanation, "
        "no code fences. Just the raw JSON object."
    )
    if response_schema:
        schema_instruction += (
            f"\n\nYour response must conform to this JSON Schema:\n"
            f"{json.dumps(response_schema, indent=2)}"
        )

    full_system = f"{system}\n\n{schema_instruction}" if system else schema_instruction

    raw = call_claude(
        prompt=prompt,
        system=full_system,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    # Strip markdown fences if Claude included them despite instructions
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (possibly ```json)
        first_newline = cleaned.index("\n")
        cleaned = cleaned[first_newline + 1 :]
    if cleaned.endswith("```"):
        cleaned = cleaned[: -3]
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("First JSON parse failed, retrying with explicit correction...")
        retry_prompt = (
            f"The following text was supposed to be valid JSON but failed to parse:\n\n"
            f"{raw}\n\n"
            f"Please return ONLY the corrected, valid JSON."
        )
        retry_raw = call_claude(
            prompt=retry_prompt,
            system=schema_instruction,
            model=model,
            temperature=0.0,
            max_tokens=max_tokens,
        )
        retry_cleaned = retry_raw.strip()
        if retry_cleaned.startswith("```"):
            first_newline = retry_cleaned.index("\n")
            retry_cleaned = retry_cleaned[first_newline + 1 :]
        if retry_cleaned.endswith("```"):
            retry_cleaned = retry_cleaned[: -3]
        return json.loads(retry_cleaned.strip())
