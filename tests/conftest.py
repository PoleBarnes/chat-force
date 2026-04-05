"""Shared pytest fixtures for the chat-force test suite.

The central concept here is the **fixture harness** at
``tests/fixtures/harness-fixture/``. Any test that needs to exercise code
which depends on a ``LoadedHarness`` pulls one of the fixtures below
rather than hand-rolling config. Tests that intentionally test bad
harness loading continue to use ``monkeypatch`` and ``tmp_path`` directly
(see ``tests/test_harness_loader.py`` for examples).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest

from pipeline.config import PipelineConfig
from pipeline.harness_loader import HarnessLoader, LoadedHarness


# ---------------------------------------------------------------------------
# Session-scoped env setup
# ---------------------------------------------------------------------------

# Fake Slack tokens referenced by tests/fixtures/harness-fixture/workspace.yaml.
# Set at session scope so any test that loads the fixture harness passes the
# HarnessLoader's required-env-var check. Tests that specifically want these
# unset use monkeypatch.delenv (function-scoped, restored on teardown).
_FIXTURE_ENV_VARS = {
    "TESTBOT_SLACK_BOT_TOKEN": "xoxb-test-fixture",
    "TESTBOT_SLACK_APP_TOKEN": "xapp-test-fixture",
}


@pytest.fixture(scope="session", autouse=True)
def _testbot_fixture_env() -> Iterator[None]:
    """Set fake Slack tokens for the fixture harness at session scope."""
    previous: dict[str, str | None] = {}
    for key, value in _FIXTURE_ENV_VARS.items():
        previous[key] = os.environ.get(key)
        os.environ[key] = value
    try:
        yield
    finally:
        for key, prior in previous.items():
            if prior is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior


# ---------------------------------------------------------------------------
# Harness fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def harness_fixture_path() -> Path:
    """Absolute path to the on-disk fixture harness."""
    return Path(__file__).parent / "fixtures" / "harness-fixture"


@pytest.fixture
def loaded_harness(harness_fixture_path: Path) -> LoadedHarness:
    """A freshly loaded ``LoadedHarness`` from the fixture harness."""
    return HarnessLoader.load(harness_fixture_path)


@pytest.fixture
def config_with_harness(
    loaded_harness: LoadedHarness, tmp_path: Path
) -> PipelineConfig:
    """A ``PipelineConfig`` with an isolated ``output_base`` and fixture harness attached."""
    return PipelineConfig(output_base=str(tmp_path), harness=loaded_harness)
