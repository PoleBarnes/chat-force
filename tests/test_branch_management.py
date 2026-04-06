"""
Tests for branch management (Task 1.4).

Covers:
- chat-force run without ticket-id → error
- Branch name derivation: ticket ID → ticket/<id>
- Branch name with --branch override
- Existing vs new branch handling
- Help output includes the run command
"""
import os
import subprocess
import tempfile
import shutil

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHAT_FORCE_BIN = os.path.join(REPO_ROOT, "bin", "chat-force")


def run_chat_force(*args, cwd=None, env=None):
    """Run bin/chat-force with given args, return CompletedProcess."""
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
    """Create a temp dir with git init + chat-force init, yield path, clean up."""
    tmpdir = tempfile.mkdtemp(prefix="chatforce-branch-test-")
    try:
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmpdir, capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmpdir, capture_output=True, check=True,
        )
        # Run chat-force init
        result = run_chat_force("init", cwd=tmpdir)
        assert result.returncode == 0, f"init failed: {result.stderr}"
        # Initial commit so we have a branch to work from
        subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmpdir, capture_output=True, check=True,
        )
        yield tmpdir
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


class TestRunCommand:
    def test_run_without_ticket_id_errors(self, git_project_dir):
        """chat-force run with no ticket-id should fail with usage error."""
        result = run_chat_force("run", cwd=git_project_dir)
        assert result.returncode != 0
        assert "ticket-id" in result.stderr.lower() or "usage" in result.stderr.lower()

    def test_help_includes_run(self):
        """Help output should mention the run command."""
        result = run_chat_force("help")
        assert result.returncode == 0
        assert "run" in result.stdout
        assert "ticket" in result.stdout.lower()


class TestBranchNaming:
    def test_default_branch_name(self, git_project_dir):
        """run PROJ-42 should create branch ticket/PROJ-42."""
        # We can't actually run claude, but we can verify the branch gets created
        # by checking git state. We'll use a trick: set PATH to exclude claude
        # so the script fails at the claude invocation but after branch creation.
        env = os.environ.copy()
        # Prepend a dir with a fake claude that exits immediately
        fake_bin = tempfile.mkdtemp(prefix="fakebin-")
        try:
            fake_claude = os.path.join(fake_bin, "claude")
            with open(fake_claude, "w") as f:
                f.write("#!/bin/bash\nexit 0\n")
            os.chmod(fake_claude, 0o755)
            env["PATH"] = fake_bin + ":" + env["PATH"]

            result = run_chat_force("run", "PROJ-42", cwd=git_project_dir, env=env)
            # Check the branch was created
            branches = subprocess.run(
                ["git", "branch", "--list", "ticket/PROJ-42"],
                cwd=git_project_dir, capture_output=True, text=True,
            )
            assert "ticket/PROJ-42" in branches.stdout
        finally:
            shutil.rmtree(fake_bin, ignore_errors=True)

    def test_branch_override(self, git_project_dir):
        """run PROJ-42 --branch custom-name should use the custom branch."""
        env = os.environ.copy()
        fake_bin = tempfile.mkdtemp(prefix="fakebin-")
        try:
            fake_claude = os.path.join(fake_bin, "claude")
            with open(fake_claude, "w") as f:
                f.write("#!/bin/bash\nexit 0\n")
            os.chmod(fake_claude, 0o755)
            env["PATH"] = fake_bin + ":" + env["PATH"]

            result = run_chat_force(
                "run", "PROJ-42", "--branch", "my-custom-branch",
                cwd=git_project_dir, env=env,
            )
            branches = subprocess.run(
                ["git", "branch", "--list", "my-custom-branch"],
                cwd=git_project_dir, capture_output=True, text=True,
            )
            assert "my-custom-branch" in branches.stdout
        finally:
            shutil.rmtree(fake_bin, ignore_errors=True)

    def test_existing_branch_checkout(self, git_project_dir):
        """If branch already exists, run should check it out (not error)."""
        # Pre-create the branch
        subprocess.run(
            ["git", "checkout", "-b", "ticket/PROJ-99"],
            cwd=git_project_dir, capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "checkout", "-"],
            cwd=git_project_dir, capture_output=True, check=True,
        )

        env = os.environ.copy()
        fake_bin = tempfile.mkdtemp(prefix="fakebin-")
        try:
            fake_claude = os.path.join(fake_bin, "claude")
            with open(fake_claude, "w") as f:
                f.write("#!/bin/bash\nexit 0\n")
            os.chmod(fake_claude, 0o755)
            env["PATH"] = fake_bin + ":" + env["PATH"]

            result = run_chat_force("run", "PROJ-99", cwd=git_project_dir, env=env)
            # Should succeed — checked out existing branch
            assert result.returncode == 0
            # Verify we're on the right branch
            current = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=git_project_dir, capture_output=True, text=True,
            )
            assert current.stdout.strip() == "ticket/PROJ-99"
        finally:
            shutil.rmtree(fake_bin, ignore_errors=True)
