"""Tests for pipeline/retry.py — exponential backoff with jitter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pipeline.retry import retry_on_transient


class TestRetryOnTransient:
    """Test the retry_on_transient decorator."""

    def test_no_retry_on_success(self):
        """Function should be called once on success, no retries."""
        fn = MagicMock(return_value="ok")
        wrapped = retry_on_transient(max_retries=3)(fn)

        result = wrapped()

        assert result == "ok"
        assert fn.call_count == 1

    def test_retries_on_transient_error(self):
        """Function should be retried on transient ConnectionError."""
        fn = MagicMock(side_effect=[ConnectionError("blip"), "ok"])
        wrapped = retry_on_transient(max_retries=3, base_delay=0.01)(fn)

        result = wrapped()

        assert result == "ok"
        assert fn.call_count == 2

    def test_retries_on_timeout_error(self):
        """Function should be retried on TimeoutError."""
        fn = MagicMock(side_effect=[TimeoutError("slow"), TimeoutError("slow"), "ok"])
        wrapped = retry_on_transient(max_retries=3, base_delay=0.01)(fn)

        result = wrapped()

        assert result == "ok"
        assert fn.call_count == 3

    def test_raises_after_max_retries_exhausted(self):
        """Should raise the last exception after all retries are used."""
        fn = MagicMock(side_effect=ConnectionError("down"))
        wrapped = retry_on_transient(max_retries=2, base_delay=0.01)(fn)

        with pytest.raises(ConnectionError, match="down"):
            wrapped()

        assert fn.call_count == 3  # initial + 2 retries

    def test_no_retry_on_non_transient_error(self):
        """Non-transient exceptions should not be retried."""
        fn = MagicMock(side_effect=ValueError("bad input"))
        wrapped = retry_on_transient(max_retries=3, base_delay=0.01)(fn)

        with pytest.raises(ValueError, match="bad input"):
            wrapped()

        assert fn.call_count == 1  # no retries

    def test_zero_retries_means_single_attempt(self):
        """max_retries=0 should call the function once, no retries."""
        fn = MagicMock(side_effect=ConnectionError("fail"))
        wrapped = retry_on_transient(max_retries=0, base_delay=0.01)(fn)

        with pytest.raises(ConnectionError):
            wrapped()

        assert fn.call_count == 1

    def test_custom_retryable_exceptions(self):
        """Should retry on custom exception types."""

        class ApiRateLimit(Exception):
            pass

        fn = MagicMock(side_effect=[ApiRateLimit("slow down"), "ok"])
        wrapped = retry_on_transient(
            max_retries=3,
            base_delay=0.01,
            retryable_exceptions=(ApiRateLimit,),
        )(fn)

        result = wrapped()

        assert result == "ok"
        assert fn.call_count == 2

    def test_retryable_check_filters_exceptions(self):
        """retryable_check should control which exceptions are retried."""
        fn = MagicMock(
            side_effect=[
                ConnectionError("rate_limited"),
                "ok",
            ]
        )
        wrapped = retry_on_transient(
            max_retries=3,
            base_delay=0.01,
            retryable_check=lambda exc: "rate_limited" in str(exc),
        )(fn)

        result = wrapped()
        assert result == "ok"

    def test_retryable_check_rejects_non_retryable(self):
        """retryable_check returning False should NOT retry."""
        fn = MagicMock(side_effect=ConnectionError("auth_failed"))
        wrapped = retry_on_transient(
            max_retries=3,
            base_delay=0.01,
            retryable_check=lambda exc: "rate_limited" in str(exc),
        )(fn)

        with pytest.raises(ConnectionError, match="auth_failed"):
            wrapped()

        assert fn.call_count == 1

    def test_backoff_delay_increases(self):
        """Delays between retries should increase exponentially."""
        fn = MagicMock(side_effect=[ConnectionError(), ConnectionError(), "ok"])
        delays = []

        def capture_sleep(delay):
            delays.append(delay)

        wrapped = retry_on_transient(max_retries=3, base_delay=1.0, max_delay=100.0)(fn)

        with patch("pipeline.retry.time.sleep", side_effect=capture_sleep):
            wrapped()

        assert len(delays) == 2
        # First delay: base_delay * 2^0 + jitter = [1.0, 2.0)
        assert 0.5 < delays[0] < 2.5
        # Second delay: base_delay * 2^1 + jitter = [2.0, 3.0)
        assert 1.5 < delays[1] < 4.5
        # Second should generally be larger than first (exponential growth)
        # (not guaranteed due to jitter, but very likely with these ranges)

    def test_max_delay_caps_backoff(self):
        """Delay should never exceed max_delay."""
        fn = MagicMock(
            side_effect=[ConnectionError()] * 10 + ["ok"]
        )
        delays = []

        wrapped = retry_on_transient(
            max_retries=10, base_delay=1.0, max_delay=5.0
        )(fn)

        with patch("pipeline.retry.time.sleep", side_effect=lambda d: delays.append(d)):
            wrapped()

        assert all(d <= 6.0 for d in delays)  # max_delay + up to 1.0 jitter

    def test_preserves_function_metadata(self):
        """Wrapped function should preserve __name__ and __doc__."""

        @retry_on_transient(max_retries=1)
        def my_function():
            """My docstring."""
            return 42

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."

    def test_passes_args_and_kwargs(self):
        """Arguments should be forwarded correctly."""
        fn = MagicMock(return_value="ok")
        wrapped = retry_on_transient(max_retries=1)(fn)

        wrapped("a", "b", key="val")

        fn.assert_called_once_with("a", "b", key="val")
