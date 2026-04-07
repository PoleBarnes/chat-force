"""
Tests for Phase 2: Three-phase CLI flow.
"""
import json
import os
import subprocess
import tempfile
import shutil

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(REPO_ROOT, "chat_force", "templates")


def run_chat_force(*args, cwd=None, env=None):
    base_env = os.environ.copy()
    base_env["PYTHONPATH"] = REPO_ROOT
    if env:
        base_env.update(env)
    return subprocess.run(
        ["python3", "-m", "chat_force.cli", *args],
        capture_output=True, text=True, cwd=cwd, env=base_env,
    )


class TestPMPrompt:
    def test_pm_prompt_exists(self):
        assert os.path.isfile(os.path.join(TEMPLATES_DIR, "pm-prompt.md"))

    def test_pm_prompt_has_role(self):
        content = open(os.path.join(TEMPLATES_DIR, "pm-prompt.md")).read()
        assert "verif" in content.lower()

    def test_pm_prompt_has_acceptance_criteria_section(self):
        content = open(os.path.join(TEMPLATES_DIR, "pm-prompt.md")).read()
        assert "acceptance criteria" in content.lower()

    def test_pm_prompt_has_pass_fail(self):
        content = open(os.path.join(TEMPLATES_DIR, "pm-prompt.md")).read()
        assert "pass" in content.lower() and "fail" in content.lower()

    def test_pm_prompt_has_output_format(self):
        content = open(os.path.join(TEMPLATES_DIR, "pm-prompt.md")).read()
        assert "## " in content


@pytest.fixture
def git_project_dir():
    tmpdir = tempfile.mkdtemp(prefix="chatforce-phase2-test-")
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


def make_fake_claude(tmpdir, script_body="exit 0"):
    fake_bin = tempfile.mkdtemp(prefix="fakebin-", dir=tmpdir)
    fake_claude = os.path.join(fake_bin, "claude")
    with open(fake_claude, "w") as f:
        f.write(f"#!/bin/bash\n{script_body}\n")
    os.chmod(fake_claude, 0o755)
    return fake_bin


class TestRunThreePhase:
    def test_run_builds_ticket_context(self, git_project_dir):
        fake_bin = make_fake_claude(
            git_project_dir,
            'cp .ticket-context /tmp/captured-ticket-context.json 2>/dev/null || true',
        )
        env = {"PATH": fake_bin + ":" + os.environ["PATH"]}
        captured = "/tmp/captured-ticket-context.json"
        if os.path.exists(captured):
            os.unlink(captured)
        try:
            result = run_chat_force("run", "PROJ-42", cwd=git_project_dir, env=env)
            assert result.returncode == 0, f"run failed: {result.stderr}"
            assert os.path.isfile(captured)
            ctx = json.loads(open(captured).read())
            assert ctx["ticket_id"] == "PROJ-42"
            assert ctx["branch"] == "ticket/PROJ-42"
        finally:
            if os.path.exists(captured):
                os.unlink(captured)

    def test_run_three_phases_output(self, git_project_dir):
        fake_bin = make_fake_claude(git_project_dir)
        env = {"PATH": fake_bin + ":" + os.environ["PATH"]}
        result = run_chat_force("run", "PROJ-42", cwd=git_project_dir, env=env)
        combined = (result.stdout + result.stderr).lower()
        assert "swarm" in combined or "execution" in combined
        assert "pm" in combined or "verification" in combined
        assert "mechanic" in combined

    def test_run_passes_ticket_context_to_swarm(self, git_project_dir):
        fake_bin = make_fake_claude(
            git_project_dir, 'echo "$@" >> /tmp/claude-args-test.txt',
        )
        env = {"PATH": fake_bin + ":" + os.environ["PATH"]}
        args_file = "/tmp/claude-args-test.txt"
        if os.path.exists(args_file):
            os.unlink(args_file)
        try:
            run_chat_force("run", "PROJ-42", cwd=git_project_dir, env=env)
            assert os.path.isfile(args_file)
            calls = open(args_file).read()
            assert "PROJ-42" in calls or "ticket" in calls.lower()
        finally:
            if os.path.exists(args_file):
                os.unlink(args_file)

    def test_run_uses_pm_prompt(self, git_project_dir):
        fake_bin = make_fake_claude(
            git_project_dir, 'echo "$@" >> /tmp/claude-pm-test.txt',
        )
        env = {"PATH": fake_bin + ":" + os.environ["PATH"]}
        args_file = "/tmp/claude-pm-test.txt"
        if os.path.exists(args_file):
            os.unlink(args_file)
        try:
            run_chat_force("run", "PROJ-42", cwd=git_project_dir, env=env)
            assert os.path.isfile(args_file)
            calls = open(args_file).read()
            assert "pm-prompt" in calls.lower() or "pm" in calls.lower()
        finally:
            if os.path.exists(args_file):
                os.unlink(args_file)

    def test_run_cleans_up_ticket_context(self, git_project_dir):
        fake_bin = make_fake_claude(git_project_dir)
        env = {"PATH": fake_bin + ":" + os.environ["PATH"]}
        result = run_chat_force("run", "PROJ-42", cwd=git_project_dir, env=env)
        assert result.returncode == 0
        assert not os.path.isfile(os.path.join(git_project_dir, ".ticket-context"))


class TestHelpOutput:
    def test_help_describes_three_phases(self):
        result = run_chat_force("help")
        assert result.returncode == 0
        lower = result.stdout.lower()
        assert "swarm" in lower or "three-phase" in lower or "pm" in lower
