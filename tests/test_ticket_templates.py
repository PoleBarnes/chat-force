"""
Tests for ticket template system (Task 1.1).

Covers:
- Template JSON schema validation (required fields)
- required_inputs entry validation (name, type, description)
- create-ticket subcommand: success with all fields
- create-ticket subcommand: error on missing fields
- create-ticket subcommand: error on unknown template
- list-templates subcommand: shows all starter templates
"""
import json
import os
import subprocess
import tempfile
import shutil

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_TEMPLATES_DIR = os.path.join(
    REPO_ROOT, "chat_force", "templates", "general", ".claude", "ticket-templates"
)

STARTER_TEMPLATES = ["general", "research-spike", "deliverable"]

REQUIRED_SCHEMA_FIELDS = [
    "name", "description", "required_inputs",
    "required_artifacts", "acceptance_criteria", "skills",
]

REQUIRED_INPUT_FIELDS = ["name", "type", "description"]


def load_template(name: str) -> dict:
    path = os.path.join(SOURCE_TEMPLATES_DIR, f"{name}.json")
    with open(path) as f:
        return json.load(f)


def run_chat_force(*args, cwd=None, env=None):
    result = subprocess.run(
        ["python3", "-m", "chat_force.cli", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env={**(env or os.environ), "PYTHONPATH": REPO_ROOT},
    )
    return result


@pytest.fixture
def project_dir():
    tmpdir = tempfile.mkdtemp(prefix="chatforce-test-")
    try:
        result = run_chat_force("init", "--tracker", "linear", cwd=tmpdir)
        assert result.returncode == 0, f"init failed: {result.stderr}"
        yield tmpdir
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


class TestTemplateSchema:
    @pytest.mark.parametrize("template_name", STARTER_TEMPLATES)
    def test_template_has_required_fields(self, template_name):
        data = load_template(template_name)
        for field in REQUIRED_SCHEMA_FIELDS:
            assert field in data, f"Template '{template_name}' missing field '{field}'"

    @pytest.mark.parametrize("template_name", STARTER_TEMPLATES)
    def test_required_inputs_have_required_fields(self, template_name):
        data = load_template(template_name)
        for i, inp in enumerate(data["required_inputs"]):
            for field in REQUIRED_INPUT_FIELDS:
                assert field in inp, (
                    f"Template '{template_name}' required_inputs[{i}] missing '{field}'"
                )

    @pytest.mark.parametrize("template_name", STARTER_TEMPLATES)
    def test_name_matches_filename(self, template_name):
        data = load_template(template_name)
        assert data["name"] == template_name

    @pytest.mark.parametrize("template_name", STARTER_TEMPLATES)
    def test_acceptance_criteria_is_list(self, template_name):
        data = load_template(template_name)
        assert isinstance(data["acceptance_criteria"], list)
        assert len(data["acceptance_criteria"]) > 0

    @pytest.mark.parametrize("template_name", STARTER_TEMPLATES)
    def test_skills_is_list(self, template_name):
        data = load_template(template_name)
        assert isinstance(data["skills"], list)


class TestInitCopiesTemplates:
    def test_init_creates_ticket_templates_dir(self, project_dir):
        tpl_dir = os.path.join(project_dir, ".claude", "ticket-templates")
        assert os.path.isdir(tpl_dir)

    def test_init_copies_all_starter_templates(self, project_dir):
        tpl_dir = os.path.join(project_dir, ".claude", "ticket-templates")
        for name in STARTER_TEMPLATES:
            path = os.path.join(tpl_dir, f"{name}.json")
            assert os.path.isfile(path), f"Template '{name}.json' should be copied by init"


class TestCreateTicket:
    def test_success_with_all_fields(self, project_dir):
        result = run_chat_force(
            "create-ticket", "--template", "general",
            "--field", "title=Fix login bug",
            "--field", "description=Users cannot log in after password reset",
            cwd=project_dir,
        )
        assert result.returncode == 0, f"Expected success, got: {result.stderr}"
        ticket = json.loads(result.stdout)
        assert ticket["template"] == "general"
        assert ticket["inputs"]["title"] == "Fix login bug"

    def test_success_deliverable_all_fields(self, project_dir):
        result = run_chat_force(
            "create-ticket", "--template", "deliverable",
            "--field", "title=Landing page",
            "--field", "description=Create a product landing page",
            "--field", "format=html",
            "--field", "audience=Developers",
            cwd=project_dir,
        )
        assert result.returncode == 0, f"Expected success, got: {result.stderr}"
        ticket = json.loads(result.stdout)
        assert ticket["template"] == "deliverable"
        assert ticket["inputs"]["format"] == "html"

    def test_error_missing_fields(self, project_dir):
        result = run_chat_force(
            "create-ticket", "--template", "deliverable",
            "--field", "title=Landing page",
            cwd=project_dir,
        )
        assert result.returncode != 0
        stderr = result.stderr
        assert "description" in stderr
        assert "format" in stderr
        assert "audience" in stderr

    def test_error_unknown_template(self, project_dir):
        result = run_chat_force(
            "create-ticket", "--template", "nonexistent",
            cwd=project_dir,
        )
        assert result.returncode != 0
        stderr = result.stderr
        assert "nonexistent" in stderr
        for name in STARTER_TEMPLATES:
            assert name in stderr

    def test_output_includes_acceptance_criteria(self, project_dir):
        result = run_chat_force(
            "create-ticket", "--template", "general",
            "--field", "title=Test",
            "--field", "description=Test description",
            cwd=project_dir,
        )
        assert result.returncode == 0
        ticket = json.loads(result.stdout)
        assert "acceptance_criteria" in ticket
        assert len(ticket["acceptance_criteria"]) > 0

    def test_output_includes_required_artifacts(self, project_dir):
        result = run_chat_force(
            "create-ticket", "--template", "research-spike",
            "--field", "title=Research AI",
            "--field", "question=How does RAG work?",
            "--field", "scope=Focus on retrieval methods",
            cwd=project_dir,
        )
        assert result.returncode == 0
        ticket = json.loads(result.stdout)
        assert "required_artifacts" in ticket
        assert len(ticket["required_artifacts"]) > 0


class TestListTemplates:
    def test_lists_all_templates(self, project_dir):
        result = run_chat_force("list-templates", cwd=project_dir)
        assert result.returncode == 0
        for name in STARTER_TEMPLATES:
            assert name in result.stdout

    def test_shows_descriptions(self, project_dir):
        result = run_chat_force("list-templates", cwd=project_dir)
        assert result.returncode == 0
        assert "Free-form ticket" in result.stdout or "free-form" in result.stdout.lower()
