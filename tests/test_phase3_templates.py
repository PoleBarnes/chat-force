"""
Tests for Phase 3: Ticket Templates and Creation.
"""
import json
import os
import subprocess
import tempfile
import shutil

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(REPO_ROOT, "chat_force", "templates")
SOURCE_TICKET_TEMPLATES = os.path.join(
    TEMPLATES_DIR, "general", ".claude", "ticket-templates"
)

REQUIRED_SCHEMA_FIELDS = [
    "name", "description", "required_inputs",
    "required_artifacts", "acceptance_criteria", "skills",
]


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
def project_dir():
    tmpdir = tempfile.mkdtemp(prefix="chatforce-phase3-test-")
    try:
        result = run_chat_force("init", "--tracker", "linear", cwd=tmpdir)
        assert result.returncode == 0, f"init failed: {result.stderr}"
        yield tmpdir
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


class TestBootstrapTemplate:
    def test_bootstrap_template_exists(self):
        assert os.path.isfile(os.path.join(SOURCE_TICKET_TEMPLATES, "bootstrap.json"))

    def test_bootstrap_has_required_schema_fields(self):
        data = json.loads(open(os.path.join(SOURCE_TICKET_TEMPLATES, "bootstrap.json")).read())
        for field in REQUIRED_SCHEMA_FIELDS:
            assert field in data

    def test_bootstrap_name_matches(self):
        data = json.loads(open(os.path.join(SOURCE_TICKET_TEMPLATES, "bootstrap.json")).read())
        assert data["name"] == "bootstrap"

    def test_bootstrap_has_project_inputs(self):
        data = json.loads(open(os.path.join(SOURCE_TICKET_TEMPLATES, "bootstrap.json")).read())
        input_names = [inp["name"] for inp in data["required_inputs"]]
        assert "description" in input_names or "project_description" in input_names
        assert "goals" in input_names
        assert "constraints" in input_names

    def test_bootstrap_copied_by_init(self, project_dir):
        path = os.path.join(project_dir, ".claude", "ticket-templates", "bootstrap.json")
        assert os.path.isfile(path)

    def test_list_templates_includes_bootstrap(self, project_dir):
        result = run_chat_force("list-templates", cwd=project_dir)
        assert result.returncode == 0
        assert "bootstrap" in result.stdout


class TestCreateTicketInteractive:
    def test_create_ticket_interactive_launches_claude(self, project_dir):
        fake_bin = tempfile.mkdtemp(prefix="fakebin-")
        try:
            fake_claude = os.path.join(fake_bin, "claude")
            with open(fake_claude, "w") as f:
                f.write('#!/bin/bash\necho "$@" >> /tmp/create-ticket-interactive-test.txt\nexit 0\n')
            os.chmod(fake_claude, 0o755)
            env = {"PATH": fake_bin + ":" + os.environ["PATH"]}
            args_file = "/tmp/create-ticket-interactive-test.txt"
            if os.path.exists(args_file):
                os.unlink(args_file)
            result = run_chat_force(
                "create-ticket", "--template", "general", "--interactive",
                cwd=project_dir, env=env,
            )
            assert os.path.isfile(args_file)
            calls = open(args_file).read()
            assert "general" in calls.lower() or "template" in calls.lower()
        finally:
            shutil.rmtree(fake_bin, ignore_errors=True)
            if os.path.exists("/tmp/create-ticket-interactive-test.txt"):
                os.unlink("/tmp/create-ticket-interactive-test.txt")

    def test_create_ticket_no_fields_no_interactive_errors(self, project_dir):
        result = run_chat_force("create-ticket", "--template", "general", cwd=project_dir)
        assert result.returncode != 0


class TestMechanicTemplateEvolution:
    def test_mechanic_prompt_has_template_section(self):
        content = open(os.path.join(TEMPLATES_DIR, "mechanic-prompt.md")).read()
        assert "template" in content.lower()

    def test_mechanic_prompt_has_ticket_template_type(self):
        content = open(os.path.join(TEMPLATES_DIR, "mechanic-prompt.md")).read()
        assert "ticket_template" in content or "ticket-template" in content.lower()


class TestHelpPhase3:
    def test_help_mentions_interactive(self):
        result = run_chat_force("help")
        assert result.returncode == 0
        assert "interactive" in result.stdout.lower() or "interview" in result.stdout.lower()
