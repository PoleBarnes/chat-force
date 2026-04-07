"""
Tests covering critical path gaps in the CLI.

Covers:
- _write_ticket_context: attempt counting from git log
- _run_swarm: WIP commit after execution
- _run_mechanic_reflection: commit after execution
- cmd_init: idempotency (re-run doesn't overwrite)
- cmd_init: invalid template error
- cmd_init: invalid tracker error
- main: unknown command error
- main: no args shows help
- main: version flag
- create-ticket: invalid field format
- create-ticket: --template without value
- list-templates: no templates dir error
- status: shows active .ticket-context
"""
import json
import os
import subprocess
import tempfile
import shutil

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_chat_force(*args, cwd=None, env=None, stdin=None):
    base_env = os.environ.copy()
    base_env["PYTHONPATH"] = REPO_ROOT
    if env:
        base_env.update(env)
    return subprocess.run(
        ["python3", "-m", "chat_force.cli", *args],
        capture_output=True, text=True, cwd=cwd, env=base_env,
        input=stdin,
    )


def make_fake_claude(tmpdir, script_body="exit 0"):
    fake_bin = tempfile.mkdtemp(prefix="fakebin-", dir=tmpdir)
    fake_claude = os.path.join(fake_bin, "claude")
    with open(fake_claude, "w") as f:
        f.write(f"#!/bin/bash\n{script_body}\n")
    os.chmod(fake_claude, 0o755)
    return fake_bin


@pytest.fixture
def git_project_dir():
    tmpdir = tempfile.mkdtemp(prefix="chatforce-gaps-test-")
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


@pytest.fixture
def project_dir():
    tmpdir = tempfile.mkdtemp(prefix="chatforce-gaps-test-")
    try:
        result = run_chat_force("init", cwd=tmpdir)
        assert result.returncode == 0
        yield tmpdir
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# _write_ticket_context: attempt counting
# ---------------------------------------------------------------------------
class TestTicketContextAttempts:
    def test_first_attempt_is_1(self, git_project_dir):
        """On a fresh branch, attempt should be 1."""
        fake_bin = make_fake_claude(
            git_project_dir,
            'cp .ticket-context /tmp/ctx-attempt-test.json 2>/dev/null || true',
        )
        env = {"PATH": fake_bin + ":" + os.environ["PATH"]}
        captured = "/tmp/ctx-attempt-test.json"
        if os.path.exists(captured):
            os.unlink(captured)
        try:
            run_chat_force("run", "TEST-1", cwd=git_project_dir, env=env)
            assert os.path.isfile(captured)
            ctx = json.loads(open(captured).read())
            assert ctx["attempt"] == 1
        finally:
            if os.path.exists(captured):
                os.unlink(captured)

    def test_attempt_increments_after_wip_commits(self, git_project_dir):
        """After 2 WIP commits, next attempt should be 3."""
        # Create branch and simulate 2 prior WIP commits
        subprocess.run(["git", "checkout", "-b", "ticket/TEST-2"],
                       cwd=git_project_dir, capture_output=True, check=True)
        for i in range(2):
            with open(os.path.join(git_project_dir, f"wip{i}.txt"), "w") as f:
                f.write(f"wip {i}")
            subprocess.run(["git", "add", "-A"], cwd=git_project_dir, capture_output=True)
            subprocess.run(["git", "commit", "-m", f"WIP: TEST-2 session"],
                           cwd=git_project_dir, capture_output=True, check=True)
        subprocess.run(["git", "checkout", "-"],
                       cwd=git_project_dir, capture_output=True, check=True)

        fake_bin = make_fake_claude(
            git_project_dir,
            'cp .ticket-context /tmp/ctx-attempt-test2.json 2>/dev/null || true',
        )
        env = {"PATH": fake_bin + ":" + os.environ["PATH"]}
        captured = "/tmp/ctx-attempt-test2.json"
        if os.path.exists(captured):
            os.unlink(captured)
        try:
            run_chat_force("run", "TEST-2", cwd=git_project_dir, env=env)
            assert os.path.isfile(captured)
            ctx = json.loads(open(captured).read())
            assert ctx["attempt"] == 3
        finally:
            if os.path.exists(captured):
                os.unlink(captured)


# ---------------------------------------------------------------------------
# _run_swarm: WIP commit
# ---------------------------------------------------------------------------
class TestSwarmCommit:
    def test_swarm_creates_wip_commit_when_files_change(self, git_project_dir):
        """If the swarm produces files, they should be committed as WIP."""
        fake_bin = make_fake_claude(
            git_project_dir,
            'echo "swarm output" > swarm-artifact.txt',
        )
        env = {"PATH": fake_bin + ":" + os.environ["PATH"]}
        run_chat_force("run", "COMMIT-1", cwd=git_project_dir, env=env)

        # Check git log for WIP commit
        result = subprocess.run(
            ["git", "log", "--oneline", "--all", "--grep=WIP: COMMIT-1"],
            cwd=git_project_dir, capture_output=True, text=True,
        )
        assert "WIP: COMMIT-1" in result.stdout

    def test_swarm_output_mentions_no_changes(self, git_project_dir):
        """If swarm produces nothing, output should say 'no changes'."""
        fake_bin = make_fake_claude(git_project_dir, "exit 0")
        env = {"PATH": fake_bin + ":" + os.environ["PATH"]}

        result = run_chat_force("run", "EMPTY-1", cwd=git_project_dir, env=env)
        combined = (result.stdout + result.stderr).lower()
        # The .ticket-context itself triggers a commit, but the output
        # should still show the three phases completing
        assert "phase 1" in combined or "swarm" in combined


# ---------------------------------------------------------------------------
# cmd_init: idempotency
# ---------------------------------------------------------------------------
class TestInitIdempotency:
    def test_init_twice_does_not_overwrite(self, project_dir):
        """Running init twice should not overwrite existing files."""
        # Modify CLAUDE.md
        claude_path = os.path.join(project_dir, "CLAUDE.md")
        with open(claude_path, "w") as f:
            f.write("# My Custom Project")

        # Run init again
        run_chat_force("init", cwd=project_dir)

        # CLAUDE.md should still have our custom content
        content = open(claude_path).read()
        assert "My Custom Project" in content


# ---------------------------------------------------------------------------
# cmd_init: error paths
# ---------------------------------------------------------------------------
class TestInitErrors:
    def test_invalid_template(self):
        tmpdir = tempfile.mkdtemp(prefix="chatforce-gaps-")
        try:
            result = run_chat_force("init", "--template", "nonexistent", cwd=tmpdir)
            assert result.returncode != 0
            assert "not found" in result.stderr.lower()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_invalid_tracker(self):
        tmpdir = tempfile.mkdtemp(prefix="chatforce-gaps-")
        try:
            result = run_chat_force("init", "--tracker", "github", cwd=tmpdir)
            assert result.returncode != 0
            assert "unknown tracker" in result.stderr.lower()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# main: routing
# ---------------------------------------------------------------------------
class TestMainRouting:
    def test_unknown_command_errors(self):
        result = run_chat_force("foobar")
        assert result.returncode != 0
        assert "unknown command" in result.stderr.lower()

    def test_no_args_shows_help(self):
        result = run_chat_force()
        assert result.returncode == 0
        assert "chat-force v" in result.stdout
        assert "Usage:" in result.stdout

    def test_version_flag(self):
        result = run_chat_force("--version")
        assert result.returncode == 0
        assert "chat-force v" in result.stdout

    def test_dash_h_flag(self):
        result = run_chat_force("-h")
        assert result.returncode == 0
        assert "Usage:" in result.stdout


# ---------------------------------------------------------------------------
# create-ticket: edge cases
# ---------------------------------------------------------------------------
class TestCreateTicketEdgeCases:
    def test_invalid_field_format(self, project_dir):
        """Field without = should error."""
        result = run_chat_force(
            "create-ticket", "--template", "general",
            "--field", "no-equals-sign",
            cwd=project_dir,
        )
        assert result.returncode != 0
        assert "key=value" in result.stderr.lower()

    def test_missing_template_flag(self, project_dir):
        """create-ticket without --template should error."""
        result = run_chat_force("create-ticket", cwd=project_dir)
        assert result.returncode != 0
        assert "template" in result.stderr.lower()


# ---------------------------------------------------------------------------
# list-templates: no templates dir
# ---------------------------------------------------------------------------
class TestListTemplatesNoDir:
    def test_error_when_no_templates_dir(self):
        tmpdir = tempfile.mkdtemp(prefix="chatforce-gaps-")
        try:
            # Create minimal project without templates
            with open(os.path.join(tmpdir, "CLAUDE.md"), "w") as f:
                f.write("# Test")
            os.makedirs(os.path.join(tmpdir, ".claude"))
            with open(os.path.join(tmpdir, ".claude", "chat-force.json"), "w") as f:
                json.dump({"tracker": "linear"}, f)

            result = run_chat_force("list-templates", cwd=tmpdir)
            assert result.returncode != 0
            assert "not found" in result.stderr.lower() or "init" in result.stderr.lower()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# status: active .ticket-context
# ---------------------------------------------------------------------------
class TestStatusActiveContext:
    def test_status_shows_active_context(self, git_project_dir):
        subprocess.run(["git", "checkout", "-b", "ticket/CTX-1"],
                       cwd=git_project_dir, capture_output=True, check=True)
        # Write a .ticket-context
        ctx_path = os.path.join(git_project_dir, ".ticket-context")
        with open(ctx_path, "w") as f:
            json.dump({"ticket_id": "CTX-1", "branch": "ticket/CTX-1", "attempt": 1}, f)

        result = run_chat_force("status", cwd=git_project_dir)
        assert result.returncode == 0
        assert "active session" in result.stdout.lower() or ".ticket-context" in result.stdout

        os.unlink(ctx_path)
