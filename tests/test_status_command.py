"""
Tests for chat-force status command.
"""
import os
import subprocess
import tempfile
import shutil

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_chat_force(*args, cwd=None, env=None):
    base_env = os.environ.copy()
    base_env["PYTHONPATH"] = REPO_ROOT
    if env:
        base_env.update(env)
    return subprocess.run(
        ["python3", "-m", "chat_force.cli", *args],
        capture_output=True, text=True, cwd=cwd, env=base_env,
    )


@pytest.fixture
def git_project_dir():
    tmpdir = tempfile.mkdtemp(prefix="chatforce-status-test-")
    try:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"],
                       cwd=tmpdir, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test"],
                       cwd=tmpdir, capture_output=True, check=True)
        result = run_chat_force("init", "--tracker", "linear", cwd=tmpdir)
        assert result.returncode == 0, f"init failed: {result.stderr}"
        subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "initial"],
                       cwd=tmpdir, capture_output=True, check=True)
        yield tmpdir
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


class TestStatusCommand:
    def test_status_runs_successfully(self, git_project_dir):
        result = run_chat_force("status", cwd=git_project_dir)
        assert result.returncode == 0

    def test_status_shows_branch(self, git_project_dir):
        result = run_chat_force("status", cwd=git_project_dir)
        current = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=git_project_dir, capture_output=True, text=True,
        )
        assert current.stdout.strip() in result.stdout

    def test_status_on_ticket_branch_shows_ticket(self, git_project_dir):
        subprocess.run(["git", "checkout", "-b", "ticket/PROJ-42"],
                       cwd=git_project_dir, capture_output=True, check=True)
        result = run_chat_force("status", cwd=git_project_dir)
        assert result.returncode == 0
        assert "PROJ-42" in result.stdout

    def test_status_shows_no_ticket_on_regular_branch(self, git_project_dir):
        result = run_chat_force("status", cwd=git_project_dir)
        combined = result.stdout.lower()
        assert "no ticket" in combined or "none" in combined or "n/a" in combined

    def test_status_shows_attempt_count(self, git_project_dir):
        subprocess.run(["git", "checkout", "-b", "ticket/PROJ-99"],
                       cwd=git_project_dir, capture_output=True, check=True)
        for i in range(2):
            with open(os.path.join(git_project_dir, f"file{i}.txt"), "w") as f:
                f.write(f"attempt {i+1}")
            subprocess.run(["git", "add", "-A"], cwd=git_project_dir, capture_output=True)
            subprocess.run(["git", "commit", "-m", f"WIP: PROJ-99 session"],
                           cwd=git_project_dir, capture_output=True, check=True)
        result = run_chat_force("status", cwd=git_project_dir)
        assert result.returncode == 0
        assert "2" in result.stdout


class TestHelpIncludesStatus:
    def test_help_has_status(self):
        result = run_chat_force("help")
        assert "status" in result.stdout.lower()
