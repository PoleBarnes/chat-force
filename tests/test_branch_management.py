"""
Tests for branch management (Task 1.4).
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
    tmpdir = tempfile.mkdtemp(prefix="chatforce-branch-test-")
    try:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"],
                       cwd=tmpdir, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test"],
                       cwd=tmpdir, capture_output=True, check=True)
        result = run_chat_force("init", cwd=tmpdir)
        assert result.returncode == 0, f"init failed: {result.stderr}"
        subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "initial"],
                       cwd=tmpdir, capture_output=True, check=True)
        yield tmpdir
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def make_fake_claude(tmpdir, script_body="exit 0"):
    fake_bin = tempfile.mkdtemp(prefix="fakebin-", dir=tmpdir)
    fake_claude = os.path.join(fake_bin, "claude")
    with open(fake_claude, "w") as f:
        f.write(f"#!/bin/bash\n{script_body}\n")
    os.chmod(fake_claude, 0o755)
    return fake_bin


class TestRunCommand:
    def test_run_without_ticket_id_errors(self, git_project_dir):
        result = run_chat_force("run", cwd=git_project_dir)
        assert result.returncode != 0
        assert "ticket-id" in result.stderr.lower() or "usage" in result.stderr.lower()

    def test_help_includes_run(self):
        result = run_chat_force("help")
        assert result.returncode == 0
        assert "run" in result.stdout
        assert "ticket" in result.stdout.lower()


class TestBranchNaming:
    def test_default_branch_name(self, git_project_dir):
        fake_bin = make_fake_claude(git_project_dir)
        env = {"PATH": fake_bin + ":" + os.environ["PATH"]}
        result = run_chat_force("run", "PROJ-42", cwd=git_project_dir, env=env)
        branches = subprocess.run(
            ["git", "branch", "--list", "ticket/PROJ-42"],
            cwd=git_project_dir, capture_output=True, text=True,
        )
        assert "ticket/PROJ-42" in branches.stdout

    def test_branch_override(self, git_project_dir):
        fake_bin = make_fake_claude(git_project_dir)
        env = {"PATH": fake_bin + ":" + os.environ["PATH"]}
        result = run_chat_force(
            "run", "PROJ-42", "--branch", "my-custom-branch",
            cwd=git_project_dir, env=env,
        )
        branches = subprocess.run(
            ["git", "branch", "--list", "my-custom-branch"],
            cwd=git_project_dir, capture_output=True, text=True,
        )
        assert "my-custom-branch" in branches.stdout

    def test_existing_branch_checkout(self, git_project_dir):
        subprocess.run(["git", "checkout", "-b", "ticket/PROJ-99"],
                       cwd=git_project_dir, capture_output=True, check=True)
        subprocess.run(["git", "checkout", "-"],
                       cwd=git_project_dir, capture_output=True, check=True)
        fake_bin = make_fake_claude(git_project_dir)
        env = {"PATH": fake_bin + ":" + os.environ["PATH"]}
        result = run_chat_force("run", "PROJ-99", cwd=git_project_dir, env=env)
        assert result.returncode == 0
        current = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=git_project_dir, capture_output=True, text=True,
        )
        assert current.stdout.strip() == "ticket/PROJ-99"
