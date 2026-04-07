"""
Tests for Phase 4: chat-force status command (Task 4.2).

Covers:
- status outside a ticket branch shows basic info
- status on a ticket branch shows ticket ID
- status shows attempt count from git log
- help includes status command
"""
import os
import subprocess
import tempfile
import shutil

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHAT_FORCE_BIN = os.path.join(REPO_ROOT, "bin", "chat-force")


def run_chat_force(*args, cwd=None, env=None):
    result = subprocess.run(
        [CHAT_FORCE_BIN, *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
    )
    return result


@pytest.fixture
def git_project_dir():
    tmpdir = tempfile.mkdtemp(prefix="chatforce-status-test-")
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


class TestStatusCommand:
    def test_status_runs_successfully(self, git_project_dir):
        result = run_chat_force("status", cwd=git_project_dir)
        assert result.returncode == 0, f"status failed: {result.stderr}"

    def test_status_shows_branch(self, git_project_dir):
        result = run_chat_force("status", cwd=git_project_dir)
        assert result.returncode == 0
        # Should show the current branch name
        current = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=git_project_dir, capture_output=True, text=True,
        )
        branch = current.stdout.strip()
        assert branch in result.stdout, f"status should show branch '{branch}'"

    def test_status_on_ticket_branch_shows_ticket(self, git_project_dir):
        """On a ticket/* branch, status should extract and show the ticket ID."""
        subprocess.run(
            ["git", "checkout", "-b", "ticket/PROJ-42"],
            cwd=git_project_dir, capture_output=True, check=True,
        )
        result = run_chat_force("status", cwd=git_project_dir)
        assert result.returncode == 0
        assert "PROJ-42" in result.stdout, "status should show ticket ID on ticket branch"

    def test_status_shows_no_ticket_on_regular_branch(self, git_project_dir):
        result = run_chat_force("status", cwd=git_project_dir)
        assert result.returncode == 0
        combined = result.stdout.lower()
        assert "no ticket" in combined or "none" in combined or "n/a" in combined, (
            "status on non-ticket branch should indicate no associated ticket"
        )

    def test_status_shows_attempt_count(self, git_project_dir):
        """After WIP commits, status should show the attempt count."""
        subprocess.run(
            ["git", "checkout", "-b", "ticket/PROJ-99"],
            cwd=git_project_dir, capture_output=True, check=True,
        )
        # Create two WIP commits
        for i in range(2):
            with open(os.path.join(git_project_dir, f"file{i}.txt"), "w") as f:
                f.write(f"attempt {i+1}")
            subprocess.run(["git", "add", "-A"], cwd=git_project_dir, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", f"WIP: PROJ-99 session"],
                cwd=git_project_dir, capture_output=True, check=True,
            )
        result = run_chat_force("status", cwd=git_project_dir)
        assert result.returncode == 0
        assert "2" in result.stdout, "status should show 2 attempts"


class TestHelpIncludesStatus:
    def test_help_has_status(self):
        result = run_chat_force("help")
        assert result.returncode == 0
        assert "status" in result.stdout.lower()
