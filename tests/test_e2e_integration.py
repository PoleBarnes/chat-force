"""End-to-end integration tests for the full mocked pipeline flow."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from pipeline.config import PipelineConfig
from pipeline.main import run_pipeline, MAX_ITERATIONS


@pytest.fixture
def pipeline_harness(tmp_path, monkeypatch):
    """Build a reusable fully mocked pipeline harness."""
    config = PipelineConfig(
        output_base=str(tmp_path),
        worker_timeout=1,
        mechanic_timeout=1,
    )

    monkeypatch.setenv("GITHUB_TOKEN", "test-github-token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")

    harness = {
        "config": config,
    }

    def _clone(payload):
        return json.loads(json.dumps(payload))

    def _bind(MockWorker, MockMechanic, MockExtractor, MockPR, MockSlack):
        worker = MagicMock(name="worker_manager")
        worker.start.return_value = "container-e2e-123"
        worker.wait_for_completion.return_value = None
        worker.is_alive.return_value = True
        worker.get_logs.return_value = "worker logs"
        worker.cleanup.return_value = None
        worker.send_feedback.return_value = None
        MockWorker.return_value = worker

        extractor = MagicMock(name="changeset_extractor")
        extractor.cleanup.return_value = None
        MockExtractor.return_value = extractor

        mechanic = MagicMock(name="mechanic_manager")
        mechanic.cleanup.return_value = None
        MockMechanic.return_value = mechanic

        pr_creator = MagicMock(name="pr_creator")
        pr_creator.create.return_value = "https://github.com/PoleBarnes/chat-force/pull/123"
        MockPR.return_value = pr_creator

        slack = MagicMock(name="slack_handler")
        slack.notify_approved.return_value = None
        slack.notify_rejected.return_value = None
        slack.notify_linear_proposal.return_value = None
        MockSlack.return_value = slack

        def set_changeset(changeset=None):
            payload = changeset or {
                "run_id": "changeset-run",
                "task": "Implement feature",
                "worker_container": worker.start.return_value,
                "git_changes": {
                    "new_files": ["feature.py"],
                    "modified_files": [],
                    "deleted_files": [],
                    "file_contents": {
                        "feature.py": "def hello(): pass",
                    },
                },
                "docker_changes": {},
                "telemetry": {},
                "agent_logs": {},
            }
            extractor.extract.side_effect = lambda *args, **kwargs: _clone(payload)
            harness["changeset"] = payload

        def set_verdicts(verdicts=None):
            payload = verdicts or {
                "approved": True,
                "pr_title": "Add feature",
                "pr_body": "Adds feature.py",
                "files_to_include": ["feature.py"],
                "disposition": "pr",
                "confidence": 0.9,
            }
            if isinstance(payload, list):
                mechanic.evaluate.side_effect = [_clone(item) for item in payload]
            else:
                mechanic.evaluate.side_effect = None
                mechanic.evaluate.return_value = _clone(payload)
            harness["verdicts"] = payload

        set_changeset()
        set_verdicts()

        harness.update(
            {
                "MockWorker": MockWorker,
                "MockMechanic": MockMechanic,
                "MockExtractor": MockExtractor,
                "MockPR": MockPR,
                "MockSlack": MockSlack,
                "worker": worker,
                "extractor": extractor,
                "mechanic": mechanic,
                "pr_creator": pr_creator,
                "slack": slack,
                "set_changeset": set_changeset,
                "set_verdicts": set_verdicts,
            }
        )
        return harness

    harness["bind"] = _bind
    return harness


@patch("pipeline.main.SlackHandler")
@patch("pipeline.main.PRCreator")
@patch("pipeline.main.ChangesetExtractor")
@patch("pipeline.main.MechanicManager")
@patch("pipeline.main.WorkerManager")
def test_e2e_happy_path_approve_creates_pr(
    MockWorker,
    MockMechanic,
    MockExtractor,
    MockPR,
    MockSlack,
    pipeline_harness,
):
    harness = pipeline_harness["bind"](MockWorker, MockMechanic, MockExtractor, MockPR, MockSlack)

    harness["set_changeset"](
        {
            "run_id": "changeset-run",
            "task": "Implement feature",
            "worker_container": "container-e2e-123",
            "git_changes": {
                "new_files": ["feature.py"],
                "modified_files": [],
                "deleted_files": [],
                "file_contents": {
                    "feature.py": "def hello(): pass",
                },
            },
            "docker_changes": {},
            "telemetry": {},
            "agent_logs": {},
        }
    )
    harness["set_verdicts"](
        {
            "approved": True,
            "pr_title": "Add feature",
            "pr_body": "Implements feature.py",
            "files_to_include": ["feature.py"],
            "disposition": "pr",
            "confidence": 0.9,
        }
    )

    summary = run_pipeline("Implement feature", harness["config"])

    harness["pr_creator"].create.assert_called_once()
    assert summary["status"] == "approved"
    assert summary["pr_url"] == "https://github.com/PoleBarnes/chat-force/pull/123"

    summary_path = os.path.join(harness["config"].output_base, summary["run_id"], "summary.json")
    with open(summary_path) as f:
        saved_summary = json.load(f)
    assert saved_summary["status"] == "approved"
    assert saved_summary["pr_url"] == summary["pr_url"]


@patch("pipeline.main.SlackHandler")
@patch("pipeline.main.PRCreator")
@patch("pipeline.main.ChangesetExtractor")
@patch("pipeline.main.MechanicManager")
@patch("pipeline.main.WorkerManager")
def test_e2e_reject_then_approve_feedback_loop(
    MockWorker,
    MockMechanic,
    MockExtractor,
    MockPR,
    MockSlack,
    pipeline_harness,
):
    harness = pipeline_harness["bind"](MockWorker, MockMechanic, MockExtractor, MockPR, MockSlack)

    harness["worker"].is_alive.return_value = True
    harness["set_verdicts"](
        [
            {
                "approved": False,
                "reason": "Missing tests",
                "feedback": ["Add unit tests"],
            },
            {
                "approved": True,
                "pr_title": "Add feature",
                "pr_body": "Adds feature and tests.",
                "files_to_include": ["feature.py"],
                "disposition": "pr",
            },
        ]
    )

    summary = run_pipeline("Implement feature", harness["config"])

    harness["worker"].send_feedback.assert_called_once()
    feedback_text = harness["worker"].send_feedback.call_args.args[0]
    assert "Missing tests" in feedback_text
    assert summary["iterations"] == 2
    assert summary["status"] == "approved"


@patch("pipeline.main.SlackHandler")
@patch("pipeline.main.PRCreator")
@patch("pipeline.main.ChangesetExtractor")
@patch("pipeline.main.MechanicManager")
@patch("pipeline.main.WorkerManager")
def test_e2e_max_iterations_exhausted(
    MockWorker,
    MockMechanic,
    MockExtractor,
    MockPR,
    MockSlack,
    pipeline_harness,
):
    harness = pipeline_harness["bind"](MockWorker, MockMechanic, MockExtractor, MockPR, MockSlack)

    harness["worker"].is_alive.return_value = True
    harness["set_verdicts"](
        [
            {
                "approved": False,
                "reason": "Still bad",
                "feedback": ["Try again"],
            }
            for _ in range(MAX_ITERATIONS)
        ]
    )

    summary = run_pipeline("Implement feature", harness["config"])

    assert harness["mechanic"].evaluate.call_count == MAX_ITERATIONS
    assert summary["status"] == "rejected"
    assert summary["iterations"] == MAX_ITERATIONS
    harness["pr_creator"].create.assert_not_called()


@patch("pipeline.main.SlackHandler")
@patch("pipeline.main.PRCreator")
@patch("pipeline.main.ChangesetExtractor")
@patch("pipeline.main.MechanicManager")
@patch("pipeline.main.WorkerManager")
def test_e2e_worker_crash_error_status(
    MockWorker,
    MockMechanic,
    MockExtractor,
    MockPR,
    MockSlack,
    pipeline_harness,
):
    harness = pipeline_harness["bind"](MockWorker, MockMechanic, MockExtractor, MockPR, MockSlack)

    harness["worker"].start.return_value = "container-timeout"
    harness["worker"].wait_for_completion.side_effect = TimeoutError("Worker did not complete")

    summary = run_pipeline("Implement feature", harness["config"])

    assert summary["status"] == "timeout"
    assert "did not complete" in summary["error"]
    harness["mechanic"].evaluate.assert_not_called()


@patch("pipeline.main.SlackHandler")
@patch("pipeline.main.PRCreator")
@patch("pipeline.main.ChangesetExtractor")
@patch("pipeline.main.MechanicManager")
@patch("pipeline.main.WorkerManager")
def test_e2e_no_changes_skips_mechanic(
    MockWorker,
    MockMechanic,
    MockExtractor,
    MockPR,
    MockSlack,
    pipeline_harness,
):
    harness = pipeline_harness["bind"](MockWorker, MockMechanic, MockExtractor, MockPR, MockSlack)

    harness["set_changeset"](
        {
            "run_id": "changeset-run",
            "task": "No-op change",
            "worker_container": "container-e2e-123",
            "git_changes": {
                "new_files": [],
                "modified_files": [],
                "deleted_files": [],
                "file_contents": {},
            },
            "docker_changes": {},
            "telemetry": {},
            "agent_logs": {},
        }
    )
    harness["set_verdicts"](
        {
            "approved": False,
            "reason": "No file changes detected",
            "disposition": "discard",
        }
    )

    summary = run_pipeline("No-op change", harness["config"])

    if harness["mechanic"].evaluate.called:
        harness["mechanic"].evaluate.assert_called_once()
        harness["pr_creator"].create.assert_not_called()
        assert summary["status"] == "rejected"
    else:
        harness["pr_creator"].create.assert_not_called()
        assert summary["status"] == "no_changes"
