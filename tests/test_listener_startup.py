"""Subprocess smoke tests for the listener's startup path.

These cover the two P0 Definition of Done items that require actually
invoking ``python -m pipeline.slack_listener`` and observing its exit
behavior:

1. Listener without ``HARNESS_PATH`` → exits 1 with the canonical error.
2. Listener with a broken harness (missing ``identity/brand.md``) →
   exits 1 naming the exact bad path.

The listener never connects to Slack in either case because harness
validation fails first, so these tests are safe to run offline.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "harness-fixture"


def _run_listener(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Invoke ``python -m pipeline.slack_listener`` with the given env.

    Uses a clean environment (no inherited ``HARNESS_PATH`` or test-fixture
    tokens) so the listener's resolution path is deterministic.
    """
    return subprocess.run(
        [sys.executable, "-m", "pipeline.slack_listener"],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _base_env() -> dict[str, str]:
    """Minimal environment for invoking the listener as a subprocess."""
    env: dict[str, str] = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
    }
    # Pass through any venv-related vars so the subprocess can import pipeline.
    for key in ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME"):
        if key in os.environ:
            env[key] = os.environ[key]
    # Explicitly do NOT pass HARNESS_PATH or TESTBOT_SLACK_* — each test
    # adds what it needs.
    return env


_CANONICAL_HARNESS_PATH_REQUIRED = (
    "HARNESS_PATH environment variable is required. "
    "Set it to an absolute path to a harness repository."
)


def test_listener_exits_without_harness_path() -> None:
    """Starting the listener without HARNESS_PATH must exit 1 with the exact
    canonical §6 error string (not a fragment). Tests a spec gate that is
    part of the public listener contract.
    """
    env = _base_env()
    # Safety: ensure HARNESS_PATH is not leaking in from the parent process.
    env.pop("HARNESS_PATH", None)

    result = _run_listener(env)

    assert result.returncode == 1, (
        f"expected exit 1, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    combined = result.stdout + result.stderr
    # Exact canonical string per spec §6.
    assert _CANONICAL_HARNESS_PATH_REQUIRED in combined, (
        f"canonical error not found verbatim in output.\n"
        f"expected substring:\n  {_CANONICAL_HARNESS_PATH_REQUIRED}\n"
        f"actual output:\n{combined}"
    )


def test_listener_exits_with_broken_harness(tmp_path: Path) -> None:
    """Starting with a harness missing identity/brand.md must exit 1 with the
    exact canonical §6 "Required identity file missing: <path>" message,
    including the absolute path to the missing file.
    """
    broken = tmp_path / "broken-harness"
    shutil.copytree(FIXTURE_PATH, broken)
    missing_file = broken / "identity" / "brand.md"
    missing_file.unlink()

    env = _base_env()
    env["HARNESS_PATH"] = str(broken)
    env["TESTBOT_SLACK_BOT_TOKEN"] = "xoxb-test-fixture"
    env["TESTBOT_SLACK_APP_TOKEN"] = "xapp-test-fixture"

    result = _run_listener(env)

    assert result.returncode == 1, (
        f"expected exit 1, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    combined = result.stdout + result.stderr
    # Exact canonical string per spec §6, including the resolved absolute
    # path to the missing file.
    expected_msg = f"Required identity file missing: {missing_file.resolve()}"
    assert expected_msg in combined, (
        f"canonical error not found verbatim in output.\n"
        f"expected substring:\n  {expected_msg}\n"
        f"actual output:\n{combined}"
    )
