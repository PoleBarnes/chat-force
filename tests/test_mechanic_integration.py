"""Real Mechanic integration tests (Tier 4).

These tests call the REAL Claude API via MechanicManager.evaluate() to
verify the structured-output verdict flow. They catch bugs in:
  - The JSON schema passed to the Claude CLI
  - The structured_output extraction from ResultMessage
  - The persona file loading
  - The verdict validation / normalization

SLOW and costs a few cents per test in API charges. Gated on
ANTHROPIC_API_KEY so they skip in environments without the token.

Run with:
    doppler run --project chat-force --config dev -- \\
        uv run --python 3.13 --with docker,"slack_sdk>=3.41.0","slack_bolt>=1.27.0",claude-agent-sdk,pytest \\
        pytest tests/test_mechanic_integration.py -v -s
"""

import os
import pytest

from pipeline.config import PipelineConfig
from pipeline.mechanic_manager import MechanicManager


def _token_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


pytestmark = [
    pytest.mark.skipif(not _token_available(), reason="ANTHROPIC_API_KEY not set"),
    pytest.mark.slow,
]


@pytest.fixture
def mechanic(tmp_path):
    config = PipelineConfig(output_base=str(tmp_path))
    return MechanicManager(config, "mechanic-integration-test")


def test_mechanic_approves_clean_changeset(mechanic):
    """A minimal, meaningful, safe changeset should be approved."""
    changeset = {
        "task": "Add a simple README with a project name",
        "git_changes": {
            "diff": "+# chat-force\n+Digital workforce platform.",
            "new_files": ["README.md"],
            "modified_files": [],
            "deleted_files": [],
            "file_contents": {"README.md": "# chat-force\nDigital workforce platform."},
        },
        "docker_changes": {},
        "telemetry": {"exit_code": 0, "duration_seconds": 3},
        "output_files": {},
        "tool_log": [{"event": "PostToolUse", "tool_name": "Write"}],
        "usage": {"input_tokens": 200, "output_tokens": 50, "total_cost_usd": 0.005},
    }

    verdict = mechanic.evaluate(changeset)

    # Schema fields that the pipeline consumes
    assert verdict.get("verdict") in ("approve", "reject")
    assert "confidence" in verdict
    assert "evaluation" in verdict
    assert "pr_title" in verdict
    assert "pr_body" in verdict
    assert "files_to_include" in verdict
    assert isinstance(verdict["files_to_include"], list)

    # Every evaluation criterion must be present
    evaluation = verdict["evaluation"]
    for criterion in ("meaningful", "correct", "safe", "minimal", "reproducible"):
        assert criterion in evaluation, f"Missing criterion: {criterion}"
        assert "pass" in evaluation[criterion]
        assert "notes" in evaluation[criterion]

    # Normalization: approved bool must be set
    assert "approved" in verdict
    assert isinstance(verdict["approved"], bool)


def test_mechanic_returns_all_required_fields(mechanic):
    """Every required field from the VERDICT_SCHEMA should be present."""
    from pipeline.mechanic_manager import VERDICT_SCHEMA

    changeset = {
        "task": "Add a comment to a Python file",
        "git_changes": {
            "diff": "+# explain this function",
            "new_files": [],
            "modified_files": ["foo.py"],
            "deleted_files": [],
            "file_contents": {"foo.py": "# explain this function\ndef foo(): pass\n"},
        },
        "docker_changes": {},
        "telemetry": {},
        "output_files": {},
        "tool_log": [{"event": "PostToolUse", "tool_name": "Edit"}],
        "usage": {"input_tokens": 150, "output_tokens": 40, "total_cost_usd": 0.003},
    }

    verdict = mechanic.evaluate(changeset)

    # Every field listed in the schema's `required` must appear in the verdict
    required_fields = VERDICT_SCHEMA["required"]
    for field in required_fields:
        assert field in verdict, f"Missing required schema field: {field}"


def test_mechanic_handles_previous_rejections(mechanic):
    """Mechanic should accept previous_rejections context without crashing.

    This verifies the feedback-loop data flow: when iteration > 1, the
    Mechanic receives history of prior rejections. The schema must
    accept this and the verdict should still be well-formed.
    """
    changeset = {
        "task": "Create a utility function",
        "git_changes": {
            "diff": "+def add(a, b): return a + b",
            "new_files": ["utils.py"],
            "modified_files": [],
            "deleted_files": [],
            "file_contents": {"utils.py": "def add(a, b): return a + b\n"},
        },
        "docker_changes": {},
        "telemetry": {},
        "output_files": {},
        "tool_log": [{"event": "PostToolUse", "tool_name": "Write"}],
        "usage": {"input_tokens": 150, "output_tokens": 40, "total_cost_usd": 0.003},
        "previous_rejections": [
            {
                "iteration": 1,
                "reason": "Missing docstring",
                "confidence": 0.8,
                "feedback": ["Add a docstring explaining what add() does"],
            }
        ],
    }

    verdict = mechanic.evaluate(changeset)

    # Should return a well-formed verdict regardless of approve/reject
    assert verdict.get("verdict") in ("approve", "reject")
    assert "confidence" in verdict
    assert "evaluation" in verdict
