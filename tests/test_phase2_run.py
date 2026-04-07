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


class TestRunCommand:
    """Run is now interactive — test what we can without launching claude."""

    def test_run_appears_in_help(self):
        result = run_chat_force("help")
        assert result.returncode == 0
        assert "run" in result.stdout.lower()

    def test_pm_prompt_exists(self):
        assert os.path.isfile(os.path.join(TEMPLATES_DIR, "pm-prompt.md"))

    def test_mechanic_prompt_exists(self):
        assert os.path.isfile(os.path.join(TEMPLATES_DIR, "mechanic-prompt.md"))
