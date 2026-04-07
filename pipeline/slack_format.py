"""Formatting helpers for Slack responses.

Currently provides the context window usage footer that is appended
to every bot response. Future: additional Block Kit formatting.
"""

from __future__ import annotations


def context_footer(usage: dict, model_context_window: int = 200_000) -> str:
    """Format context window usage as a one-line footer string.

    Args:
        usage: Dict from ``WorkerManager.get_usage()`` with keys
            ``input_tokens``, ``output_tokens``, ``total_cost_usd``.
        model_context_window: Max context window size in tokens.
            Defaults to 200k (Claude Opus/Sonnet). Override via
            ``workspace.yaml.bot.model_context_window``.

    Returns:
        A one-line string like ``Context: 🟢 23% | $0.42``.
        On any error, returns ``Context: unknown``.
    """
    try:
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        total_tokens = input_tokens + output_tokens
        cost = float(usage.get("total_cost_usd", 0.0) or 0.0)

        if model_context_window <= 0:
            return "Context: unknown"

        pct = total_tokens / model_context_window * 100

        if pct < 40:
            indicator = "\U0001f7e2"  # 🟢
        elif pct < 85:
            indicator = "\U0001f7e1"  # 🟡
        else:
            indicator = "\U0001f534"  # 🔴

        return f"Context: {indicator} {pct:.0f}% | ${cost:.2f}"

    except Exception:
        return "Context: unknown"
