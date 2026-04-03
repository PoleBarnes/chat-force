"""Extract response text from OpenClaw JSON output."""

from __future__ import annotations

import json
import logging
import re

log = logging.getLogger(__name__)


def parse_response(raw: str) -> str:
    """Extract text response from OpenClaw JSON output.

    Returns all text payloads joined with newlines.
    Handles malformed JSON gracefully (returns empty string).

    The raw output may have non-JSON prefix lines (log lines from stderr
    mixed in). We find the JSON starting with ``{"payloads"`` and parse
    from there.
    """
    if not raw or not raw.strip():
        return ""

    # Try to locate the JSON object in the raw output
    json_str = _extract_json(raw)
    if json_str is None:
        log.warning("Could not find JSON payload in OpenClaw output (%d chars)", len(raw))
        return ""

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        log.warning("Failed to parse OpenClaw JSON: %s", exc)
        return ""

    payloads = data.get("payloads")
    if not isinstance(payloads, list):
        log.warning("OpenClaw JSON missing 'payloads' list")
        return ""

    texts = []
    for entry in payloads:
        if isinstance(entry, dict):
            text = entry.get("text")
            if text:
                texts.append(text)

    return "\n".join(texts)


def _extract_json(raw: str) -> str | None:
    """Find the first JSON object starting with {"payloads" in the raw output."""
    # Fast path: the whole string is valid JSON
    stripped = raw.strip()
    if stripped.startswith("{"):
        return stripped

    # Look for the JSON object start pattern
    match = re.search(r'\{"payloads"', raw)
    if match is None:
        return None

    # Extract from the match to end-of-string and try to parse
    candidate = raw[match.start():]

    # Find the matching closing brace by tracking nesting
    depth = 0
    in_string = False
    escape = False
    for i, ch in enumerate(candidate):
        if escape:
            escape = False
            continue
        if ch == "\\":
            if in_string:
                escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return candidate[: i + 1]

    # If we couldn't find balanced braces, return the whole candidate
    return candidate
