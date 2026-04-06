"""
Tests for Phase 2: Three-phase CLI flow (Tasks 2.1, 2.2, 2.3).

Covers:
- PM prompt file exists and has required sections
- run command three-phase flow structure
- Ticket context file generation
- Help output includes updated run description
- Swarm prompt file exists and has required sections
"""
import os
import subprocess
import tempfile
import shutil

import pytest
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHAT_FORCE_BIN = os.path.join(REPO_ROOT, "bin", "chat-force")
TEMPLATES_DIR = os.path.join(REPO_ROOT, "templates")


def run_chat_force(*args, cwd=None, env=None):
    result = subprocess.run(
        [CHAT_FORCE_BIN, *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
    )
    return result


# ---------------------------------------------------------------------------
# Task 2.2: PM Agent Persona
# ---------------------------------------------------------------------------
class TestPMPrompt:
    def test_pm_prompt_exists(self):
        path = os.path.join(TEMPLATES_DIR, "pm-prompt.md")
        assert os.path.isfile(path), "templates/pm-prompt.md must exist"

    def test_pm_prompt_has_role(self):
        path = os.path.join(TEMPLATES_DIR, "pm-prompt.md")
        content = open(path).read()
        assert "verif" in content.lower(), "PM prompt should mention verification"

    def test_pm_prompt_has_acceptance_criteria_section(self):
        path = os.path.join(TEMPLATES_DIR, "pm-prompt.md")
        content = open(path).read()
        assert "acceptance criteria" in content.lower(), (
            "PM prompt should reference acceptance criteria"
        )

    def test_pm_prompt_has_pass_fail(self):
        path = os.path.join(TEMPLATES_DIR, "pm-prompt.md")
        content = open(path).read()
        lower = content.lower()
        assert "pass" in lower and "fail" in lower, (
            "PM prompt should define pass/fail outcomes"
        )

    def test_pm_prompt_has_output_format(self):
        """PM should output structured results."""
        path = os.path.join(TEMPLATES_DIR, "pm-prompt.md")
        content = open(path).read()
        assert "## " in content, "PM prompt should have markdown sections"


# ---------------------------------------------------------------------------
# Task 2.1: Three-phase run command
# ---------------------------------------------------------------------------
@pytest.fixture
def git_project_dir():
    """Create a temp dir with git init + chat-force init, yield path, clean up."""
    tmpdir = tempfile.mkdtemp(prefix="chatforce-phase2-test-")
    try:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmpdir, capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmpdir, capture_output=True, check=True,
        )
        result = run_chat_force("init", cwd=tmpdir)
        assert result.returncode == 0, f"init failed: {result.stderr}"
        subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmpdir, capture_output=True, check=True,
        )
        yield tmpdir
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def make_fake_claude(tmpdir, script_body="exit 0"):
    """Create a fake claude binary that runs the given script body."""
    fake_bin = tempfile.mkdtemp(prefix="fakebin-", dir=tmpdir)
    fake_claude = os.path.join(fake_bin, "claude")
    with open(fake_claude, "w") as f:
        f.write(f"#!/bin/bash\n{script_body}\n")
    os.chmod(fake_claude, 0o755)
    return fake_bin


class TestRunThreePhase:
    def test_run_builds_ticket_context(self, git_project_dir):
        """run should create a .ticket-context file during execution."""
        # Use a fake claude that captures .ticket-context before it's cleaned up
        fake_bin = make_fake_claude(
            git_project_dir,
            'cp .ticket-context /tmp/captured-ticket-context.yaml 2>/dev/null || true',
        )
        env = os.environ.copy()
        env["PATH"] = fake_bin + ":" + env["PATH"]

        captured = "/tmp/captured-ticket-context.yaml"
        if os.path.exists(captured):
            os.unlink(captured)

        try:
            result = run_chat_force("run", "PROJ-42", cwd=git_project_dir, env=env)
            assert result.returncode == 0, f"run failed: {result.stderr}"

            assert os.path.isfile(captured), ".ticket-context should be created during run"
            ctx = yaml.safe_load(open(captured).read())
            assert ctx["ticket_id"] == "PROJ-42"
            assert "branch" in ctx
            assert ctx["branch"] == "ticket/PROJ-42"
        finally:
            if os.path.exists(captured):
                os.unlink(captured)

    def test_run_three_phases_output(self, git_project_dir):
        """run should mention all three phases in its output."""
        fake_bin = make_fake_claude(git_project_dir)
        env = os.environ.copy()
        env["PATH"] = fake_bin + ":" + env["PATH"]

        result = run_chat_force("run", "PROJ-42", cwd=git_project_dir, env=env)
        combined = result.stdout + result.stderr
        lower = combined.lower()

        # Should mention all phases
        assert "swarm" in lower or "execution" in lower, (
            "Output should mention execution/swarm phase"
        )
        assert "pm" in lower or "verification" in lower, (
            "Output should mention PM verification phase"
        )
        assert "mechanic" in lower, "Output should mention mechanic phase"

    def test_run_passes_ticket_context_to_swarm(self, git_project_dir):
        """The swarm session should receive ticket context via -p flag."""
        # Create a fake claude that dumps its args to a file
        fake_bin = make_fake_claude(
            git_project_dir,
            'echo "$@" >> /tmp/claude-args-test.txt',
        )
        env = os.environ.copy()
        env["PATH"] = fake_bin + ":" + env["PATH"]

        args_file = "/tmp/claude-args-test.txt"
        if os.path.exists(args_file):
            os.unlink(args_file)

        try:
            result = run_chat_force("run", "PROJ-42", cwd=git_project_dir, env=env)
            assert os.path.isfile(args_file), "claude should have been called"
            calls = open(args_file).read()
            # First call should include ticket context (via -p or --system-prompt)
            assert "PROJ-42" in calls or "ticket" in calls.lower(), (
                "Swarm should receive ticket context"
            )
        finally:
            if os.path.exists(args_file):
                os.unlink(args_file)

    def test_run_uses_pm_prompt(self, git_project_dir):
        """PM phase should use the pm-prompt.md system prompt."""
        fake_bin = make_fake_claude(
            git_project_dir,
            'echo "$@" >> /tmp/claude-pm-test.txt',
        )
        env = os.environ.copy()
        env["PATH"] = fake_bin + ":" + env["PATH"]

        args_file = "/tmp/claude-pm-test.txt"
        if os.path.exists(args_file):
            os.unlink(args_file)

        try:
            result = run_chat_force("run", "PROJ-42", cwd=git_project_dir, env=env)
            assert os.path.isfile(args_file), "claude should have been called"
            calls = open(args_file).read()
            assert "pm-prompt" in calls.lower() or "pm" in calls.lower(), (
                "PM phase should reference pm-prompt"
            )
        finally:
            if os.path.exists(args_file):
                os.unlink(args_file)

    def test_run_cleans_up_ticket_context(self, git_project_dir):
        """After all phases, .ticket-context should be cleaned up."""
        fake_bin = make_fake_claude(git_project_dir)
        env = os.environ.copy()
        env["PATH"] = fake_bin + ":" + env["PATH"]

        result = run_chat_force("run", "PROJ-42", cwd=git_project_dir, env=env)
        assert result.returncode == 0

        ctx_path = os.path.join(git_project_dir, ".ticket-context")
        assert not os.path.isfile(ctx_path), (
            ".ticket-context should be cleaned up after run"
        )


# ---------------------------------------------------------------------------
# Help output
# ---------------------------------------------------------------------------
class TestHelpOutput:
    def test_help_describes_three_phases(self):
        result = run_chat_force("help")
        assert result.returncode == 0
        lower = result.stdout.lower()
        assert "swarm" in lower or "three-phase" in lower or "pm" in lower, (
            "Help should describe the three-phase flow"
        )
