"""
Tests for ticket template system (Task 1.1).

Covers:
- Template YAML schema validation (required fields)
- required_inputs entry validation (name, type, description)
- create-ticket subcommand: success with all fields
- create-ticket subcommand: error on missing fields
- create-ticket subcommand: error on unknown template
- list-templates subcommand: shows all 3 starter templates
"""
import os
import subprocess
import tempfile
import shutil

import pytest
import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHAT_FORCE_BIN = os.path.join(REPO_ROOT, "bin", "chat-force")
SOURCE_TEMPLATES_DIR = os.path.join(
    REPO_ROOT, "templates", "general", ".claude", "ticket-templates"
)

STARTER_TEMPLATES = ["general", "research-spike", "deliverable"]

REQUIRED_SCHEMA_FIELDS = [
    "name",
    "description",
    "required_inputs",
    "required_artifacts",
    "acceptance_criteria",
    "skills",
]

REQUIRED_INPUT_FIELDS = ["name", "type", "description"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_template(name: str) -> dict:
    """Load a starter template YAML from the source templates dir."""
    path = os.path.join(SOURCE_TEMPLATES_DIR, f"{name}.yaml")
    with open(path) as f:
        return yaml.safe_load(f)


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
def project_dir():
    """Create a temp dir, run chat-force init, yield the path, then clean up."""
    tmpdir = tempfile.mkdtemp(prefix="chatforce-test-")
    try:
        result = run_chat_force("init", cwd=tmpdir)
        assert result.returncode == 0, f"init failed: {result.stderr}"
        yield tmpdir
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------
class TestTemplateSchema:
    """Validate that each starter template has all required schema fields."""

    @pytest.mark.parametrize("template_name", STARTER_TEMPLATES)
    def test_template_has_required_fields(self, template_name):
        data = load_template(template_name)
        for field in REQUIRED_SCHEMA_FIELDS:
            assert field in data, (
                f"Template '{template_name}' is missing required field '{field}'"
            )

    @pytest.mark.parametrize("template_name", STARTER_TEMPLATES)
    def test_required_inputs_have_required_fields(self, template_name):
        data = load_template(template_name)
        for i, inp in enumerate(data["required_inputs"]):
            for field in REQUIRED_INPUT_FIELDS:
                assert field in inp, (
                    f"Template '{template_name}' required_inputs[{i}] "
                    f"is missing field '{field}'"
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


# ---------------------------------------------------------------------------
# init copies ticket-templates into project
# ---------------------------------------------------------------------------
class TestInitCopiesTemplates:
    def test_init_creates_ticket_templates_dir(self, project_dir):
        tpl_dir = os.path.join(project_dir, ".claude", "ticket-templates")
        assert os.path.isdir(tpl_dir), (
            ".claude/ticket-templates/ should exist after init"
        )

    def test_init_copies_all_starter_templates(self, project_dir):
        tpl_dir = os.path.join(project_dir, ".claude", "ticket-templates")
        for name in STARTER_TEMPLATES:
            path = os.path.join(tpl_dir, f"{name}.yaml")
            assert os.path.isfile(path), (
                f"Template '{name}.yaml' should be copied by init"
            )


# ---------------------------------------------------------------------------
# create-ticket subcommand
# ---------------------------------------------------------------------------
class TestCreateTicket:
    def test_success_with_all_fields(self, project_dir):
        """create-ticket with all required fields should succeed and output YAML."""
        result = run_chat_force(
            "create-ticket",
            "--template", "general",
            "--field", "title=Fix login bug",
            "--field", "description=Users cannot log in after password reset",
            cwd=project_dir,
        )
        assert result.returncode == 0, f"Expected success, got: {result.stderr}"
        # Output should be valid YAML containing the ticket data
        ticket = yaml.safe_load(result.stdout)
        assert ticket is not None
        assert ticket["template"] == "general"
        assert ticket["inputs"]["title"] == "Fix login bug"
        assert ticket["inputs"]["description"] == "Users cannot log in after password reset"

    def test_success_deliverable_all_fields(self, project_dir):
        """create-ticket with deliverable template and all fields."""
        result = run_chat_force(
            "create-ticket",
            "--template", "deliverable",
            "--field", "title=Landing page",
            "--field", "description=Create a product landing page",
            "--field", "format=html",
            "--field", "audience=Developers",
            cwd=project_dir,
        )
        assert result.returncode == 0, f"Expected success, got: {result.stderr}"
        ticket = yaml.safe_load(result.stdout)
        assert ticket["template"] == "deliverable"
        assert ticket["inputs"]["format"] == "html"

    def test_error_missing_fields(self, project_dir):
        """create-ticket with missing required fields should fail and list them."""
        result = run_chat_force(
            "create-ticket",
            "--template", "deliverable",
            "--field", "title=Landing page",
            # missing: description, format, audience
            cwd=project_dir,
        )
        assert result.returncode != 0, "Should fail when fields are missing"
        stderr = result.stderr
        assert "description" in stderr, "Error should mention missing 'description'"
        assert "format" in stderr, "Error should mention missing 'format'"
        assert "audience" in stderr, "Error should mention missing 'audience'"

    def test_error_unknown_template(self, project_dir):
        """create-ticket with non-existent template should fail with useful error."""
        result = run_chat_force(
            "create-ticket",
            "--template", "nonexistent",
            cwd=project_dir,
        )
        assert result.returncode != 0, "Should fail for unknown template"
        stderr = result.stderr
        assert "nonexistent" in stderr, "Error should mention the bad template name"
        # Should list available templates
        for name in STARTER_TEMPLATES:
            assert name in stderr, (
                f"Error should list available template '{name}'"
            )

    def test_output_includes_acceptance_criteria(self, project_dir):
        """The output ticket YAML should include acceptance_criteria from the template."""
        result = run_chat_force(
            "create-ticket",
            "--template", "general",
            "--field", "title=Test",
            "--field", "description=Test description",
            cwd=project_dir,
        )
        assert result.returncode == 0
        ticket = yaml.safe_load(result.stdout)
        assert "acceptance_criteria" in ticket
        assert len(ticket["acceptance_criteria"]) > 0

    def test_output_includes_required_artifacts(self, project_dir):
        """The output ticket YAML should include required_artifacts from the template."""
        result = run_chat_force(
            "create-ticket",
            "--template", "research-spike",
            "--field", "title=Research AI",
            "--field", "question=How does RAG work?",
            "--field", "scope=Focus on retrieval methods",
            cwd=project_dir,
        )
        assert result.returncode == 0
        ticket = yaml.safe_load(result.stdout)
        assert "required_artifacts" in ticket
        assert len(ticket["required_artifacts"]) > 0


# ---------------------------------------------------------------------------
# list-templates subcommand
# ---------------------------------------------------------------------------
class TestListTemplates:
    def test_lists_all_templates(self, project_dir):
        """list-templates should show all 3 starter templates."""
        result = run_chat_force("list-templates", cwd=project_dir)
        assert result.returncode == 0, f"Expected success, got: {result.stderr}"
        stdout = result.stdout
        for name in STARTER_TEMPLATES:
            assert name in stdout, (
                f"list-templates output should include '{name}'"
            )

    def test_shows_descriptions(self, project_dir):
        """list-templates should show the description for each template."""
        result = run_chat_force("list-templates", cwd=project_dir)
        assert result.returncode == 0
        stdout = result.stdout
        # Check that at least the general template's description appears
        assert "Free-form ticket" in stdout or "free-form" in stdout.lower(), (
            "list-templates should show template descriptions"
        )
