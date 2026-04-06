"""Tests for pipeline/slack_format.py — context footer formatting."""

from __future__ import annotations

from pipeline.slack_format import context_footer


class TestContextFooter:
    """Test context window usage footer formatting."""

    def test_green_under_40_percent(self):
        usage = {"input_tokens": 30000, "output_tokens": 10000, "total_cost_usd": 0.42}
        result = context_footer(usage, model_context_window=200_000)
        assert "\U0001f7e2" in result  # 🟢
        assert "20%" in result
        assert "$0.42" in result

    def test_yellow_between_40_and_85(self):
        usage = {"input_tokens": 80000, "output_tokens": 20000, "total_cost_usd": 1.50}
        result = context_footer(usage, model_context_window=200_000)
        assert "\U0001f7e1" in result  # 🟡
        assert "50%" in result

    def test_red_above_85(self):
        usage = {"input_tokens": 160000, "output_tokens": 20000, "total_cost_usd": 3.00}
        result = context_footer(usage, model_context_window=200_000)
        assert "\U0001f534" in result  # 🔴
        assert "90%" in result

    def test_zero_usage(self):
        usage = {"input_tokens": 0, "output_tokens": 0, "total_cost_usd": 0.0}
        result = context_footer(usage, model_context_window=200_000)
        assert "\U0001f7e2" in result  # 🟢
        assert "0%" in result
        assert "$0.00" in result

    def test_empty_usage_dict(self):
        result = context_footer({})
        assert "\U0001f7e2" in result  # 🟢 (0 tokens)

    def test_none_values_in_usage(self):
        usage = {"input_tokens": None, "output_tokens": None, "total_cost_usd": None}
        result = context_footer(usage)
        assert "Context:" in result

    def test_invalid_context_window_returns_unknown(self):
        usage = {"input_tokens": 1000, "output_tokens": 500}
        result = context_footer(usage, model_context_window=0)
        assert result == "Context: unknown"

    def test_cost_formatting(self):
        usage = {"input_tokens": 1000, "output_tokens": 500, "total_cost_usd": 0.003}
        result = context_footer(usage)
        assert "$0.00" in result  # rounds to 2 decimal places

    def test_boundary_at_40_percent(self):
        """Exactly 40% should be yellow, not green."""
        usage = {"input_tokens": 80000, "output_tokens": 0, "total_cost_usd": 0}
        result = context_footer(usage, model_context_window=200_000)
        assert "\U0001f7e1" in result  # 🟡

    def test_boundary_at_85_percent(self):
        """Exactly 85% should be red, not yellow."""
        usage = {"input_tokens": 170000, "output_tokens": 0, "total_cost_usd": 0}
        result = context_footer(usage, model_context_window=200_000)
        assert "\U0001f534" in result  # 🔴
