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
    mixed in).  We find the *last* JSON object containing ``"payloads"``
    and parse from there — the last one is the actual OpenClaw response
    when multiple JSON blobs or log lines are present.
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

    payloads = data.get("payloads") or data.get("result", {}).get("payloads")
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
    """Find the last JSON object containing ``"payloads"`` in the raw output.

    OpenClaw CLI output often has log lines (and possibly other JSON blobs)
    before the actual response.  We search for every ``{"payloads"`` occurrence,
    extract each balanced JSON object, and return the last valid one.  This
    handles mixed log output and multiple JSON objects reliably.

    When ``payloads`` is nested under a ``result`` key (the newer OpenClaw
    envelope format), the regex still matches the inner ``{"payloads"`` inside
    the ``result`` value.  The full-blob fallback and per-line fallback also
    check for ``result.payloads``.
    """
    # Collect all candidate positions where '{"payloads"' appears
    matches = list(re.finditer(r'\{"payloads"', raw))

    if matches:
        # Walk matches in reverse — the last one is most likely the real response
        for match in reversed(matches):
            candidate = _extract_balanced_json(raw, match.start())
            if candidate is not None:
                return candidate

    # Fallback: no '{"payloads"' found — try to find *any* top-level JSON object.
    # This handles the edge case where the output is a single clean JSON blob
    # that starts with a different key order (e.g. {"meta":..., "payloads":...}).
    stripped = raw.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        # Validate it's actually parseable JSON before returning
        try:
            json.loads(stripped)
            return stripped
        except json.JSONDecodeError:
            pass

    # Last resort: try to find any JSON object on individual lines
    for line in reversed(raw.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                data = json.loads(line)
                if "payloads" in data:
                    return line
                if isinstance(data.get("result"), dict) and "payloads" in data["result"]:
                    return line
            except json.JSONDecodeError:
                continue

    return None


def _extract_balanced_json(raw: str, start: int) -> str | None:
    """Extract a balanced JSON object from *raw* beginning at *start*.

    Tracks brace nesting while respecting JSON string escaping.
    Returns the substring for the balanced object, or ``None`` if the
    braces never balance.
    """
    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(raw)):
        ch = raw[i]
        if escape:
            escape = False
            continue
        if in_string:
            if ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        # Outside a string
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return raw[start : i + 1]

    return None
