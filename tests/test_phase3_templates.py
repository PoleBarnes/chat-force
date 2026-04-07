"""
Tests for Phase 3: Ticket Templates and Creation (Tasks 3.1, 3.2, 3.3).

Covers:
- Bootstrap template schema validation
- create-ticket --interactive flag triggers Claude CLI
- create-ticket without --field args and without --interactive errors
- Mechanic prompt includes template evolution section
- init --bootstrap flag present in help
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
SOURCE_TICKET_TEMPLATES = os.path.join(
    REPO_ROOT, "templates", "general", ".claude", "ticket-templates"
)

REQUIRED_SCHEMA_FIELDS = [
    "name", "description", "required_inputs",
    "required_artifacts", "acceptance_criteria", "skills",
]


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
def project_dir():
    tmpdir = tempfile.mkdtemp(prefix="chatforce-phase3-test-")
    try:
        result = run_chat_force("init", cwd=tmpdir)
        assert result.returncode == 0, f"init failed: {result.stderr}"
        yield tmpdir
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Task 3.2: Bootstrap Template
# ---------------------------------------------------------------------------
class TestBootstrapTemplate:
    def test_bootstrap_template_exists(self):
        path = os.path.join(SOURCE_TICKET_TEMPLATES, "bootstrap.yaml")
        assert os.path.isfile(path), "bootstrap.yaml must exist in source templates"

    def test_bootstrap_has_required_schema_fields(self):
        path = os.path.join(SOURCE_TICKET_TEMPLATES, "bootstrap.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        for field in REQUIRED_SCHEMA_FIELDS:
            assert field in data, f"bootstrap.yaml missing field '{field}'"

    def test_bootstrap_name_matches(self):
        path = os.path.join(SOURCE_TICKET_TEMPLATES, "bootstrap.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data["name"] == "bootstrap"

    def test_bootstrap_has_project_inputs(self):
        """Bootstrap should require project description, goals, constraints."""
        path = os.path.join(SOURCE_TICKET_TEMPLATES, "bootstrap.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        input_names = [inp["name"] for inp in data["required_inputs"]]
        assert "description" in input_names or "project_description" in input_names
        assert "goals" in input_names
        assert "constraints" in input_names

    def test_bootstrap_copied_by_init(self, project_dir):
        """init should copy bootstrap.yaml into the project."""
        path = os.path.join(project_dir, ".claude", "ticket-templates", "bootstrap.yaml")
        assert os.path.isfile(path), "bootstrap.yaml should be copied by init"

    def test_list_templates_includes_bootstrap(self, project_dir):
        result = run_chat_force("list-templates", cwd=project_dir)
        assert result.returncode == 0
        assert "bootstrap" in result.stdout


# ---------------------------------------------------------------------------
# Task 3.1: create-ticket with Linear / interactive mode
# ---------------------------------------------------------------------------
class TestCreateTicketInteractive:
    def test_create_ticket_interactive_launches_claude(self, project_dir):
        """create-ticket --interactive should launch Claude CLI for field gathering."""
        fake_bin = tempfile.mkdtemp(prefix="fakebin-")
        try:
            fake_claude = os.path.join(fake_bin, "claude")
            with open(fake_claude, "w") as f:
                f.write('#!/bin/bash\necho "$@" >> /tmp/create-ticket-interactive-test.txt\nexit 0\n')
            os.chmod(fake_claude, 0o755)
            env = os.environ.copy()
            env["PATH"] = fake_bin + ":" + env["PATH"]

            args_file = "/tmp/create-ticket-interactive-test.txt"
            if os.path.exists(args_file):
                os.unlink(args_file)

            result = run_chat_force(
                "create-ticket", "--template", "general", "--interactive",
                cwd=project_dir, env=env,
            )
            # Should have called claude
            assert os.path.isfile(args_file), "Interactive mode should launch Claude CLI"
            calls = open(args_file).read()
            assert "general" in calls.lower() or "template" in calls.lower()
        finally:
            shutil.rmtree(fake_bin, ignore_errors=True)
            if os.path.exists("/tmp/create-ticket-interactive-test.txt"):
                os.unlink("/tmp/create-ticket-interactive-test.txt")

    def test_create_ticket_no_fields_no_interactive_errors(self, project_dir):
        """create-ticket without fields and without --interactive should error."""
        result = run_chat_force(
            "create-ticket", "--template", "general",
            cwd=project_dir,
        )
        assert result.returncode != 0, "Should fail without fields or --interactive"


# ---------------------------------------------------------------------------
# Task 3.3: Mechanic Template Evolution
# ---------------------------------------------------------------------------
class TestMechanicTemplateEvolution:
    def test_mechanic_prompt_has_template_section(self):
        """Mechanic prompt should include template evolution analysis."""
        path = os.path.join(TEMPLATES_DIR, "mechanic-prompt.md")
        content = open(path).read()
        assert "template" in content.lower(), (
            "Mechanic prompt should mention templates"
        )

    def test_mechanic_prompt_has_ticket_template_type(self):
        """Mechanic proposal types should include ticket_template."""
        path = os.path.join(TEMPLATES_DIR, "mechanic-prompt.md")
        content = open(path).read()
        assert "ticket_template" in content or "ticket-template" in content.lower(), (
            "Mechanic should support ticket_template proposal type"
        )


# ---------------------------------------------------------------------------
# Help output
# ---------------------------------------------------------------------------
class TestHelpPhase3:
    def test_help_mentions_interactive(self):
        result = run_chat_force("help")
        assert result.returncode == 0
        assert "interactive" in result.stdout.lower() or "interview" in result.stdout.lower()
