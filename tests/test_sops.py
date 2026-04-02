"""Validate SOP YAML files.

SOPs live in:
  - sops/ (platform-level SOP templates and definitions)

Each SOP must be valid YAML with specific required fields and a coherent
step structure including approval gates.
"""

from pathlib import Path
from typing import Any

import yaml
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# All directories that may contain SOP YAML files
SOP_DIRS = [
    PROJECT_ROOT / "sops",
]

REQUIRED_SOP_FIELDS = {"name", "version", "description", "input_schema", "steps", "output_schema"}


def _collect_sop_files() -> list[Path]:
    """Gather all .yaml files from SOP directories."""
    files = []
    for sop_dir in SOP_DIRS:
        if sop_dir.is_dir():
            files.extend(sorted(sop_dir.glob("*.yaml")))
    return files


def _load_sop(path: Path) -> dict[str, Any]:
    """Load and return a parsed SOP YAML file."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# -------------------------------------------------------------------------
# Tests
# -------------------------------------------------------------------------


class TestSOPParsing:
    """Test that all SOP files parse as valid YAML."""

    @pytest.fixture
    def sop_files(self):
        files = _collect_sop_files()
        assert len(files) >= 4, (
            f"Expected at least 4 SOP files (3 workspace + 1 template), found {len(files)}"
        )
        return files

    def test_all_sops_are_valid_yaml(self, sop_files):
        """Every .yaml file in SOP directories must parse without errors."""
        for sop_path in sop_files:
            try:
                data = _load_sop(sop_path)
                assert isinstance(data, dict), (
                    f"{sop_path.name}: YAML parsed to {type(data).__name__}, expected dict"
                )
            except yaml.YAMLError as exc:
                pytest.fail(f"{sop_path.name}: YAML parse error: {exc}")


class TestSOPStructure:
    """Test that SOPs have the required structure."""

    @pytest.fixture
    def loaded_sops(self):
        return [(f, _load_sop(f)) for f in _collect_sop_files()]

    def test_sop_has_required_fields(self, loaded_sops):
        """Each SOP must have all required top-level fields."""
        for sop_path, data in loaded_sops:
            missing = REQUIRED_SOP_FIELDS - set(data.keys())
            assert not missing, (
                f"{sop_path.name}: missing required fields: {missing}"
            )

    def test_sop_steps_have_valid_structure(self, loaded_sops):
        """Each step must have id and description.
        Task steps need specialist. Approval gates need type."""
        for sop_path, data in loaded_sops:
            steps = data.get("steps", [])
            for i, step in enumerate(steps):
                assert "id" in step, (
                    f"{sop_path.name}: step {i} missing 'id'"
                )
                assert "description" in step, (
                    f"{sop_path.name}: step '{step.get('id', i)}' missing 'description'"
                )
                step_type = step.get("type", "task")
                if step_type == "task":
                    # Task steps should have a specialist (or inherit default)
                    assert "specialist" in step or step_type == "task", (
                        f"{sop_path.name}: task step '{step['id']}' missing 'specialist'"
                    )
                elif step_type == "approval_gate":
                    # Approval gates must declare their type
                    assert step.get("type") == "approval_gate", (
                        f"{sop_path.name}: step '{step['id']}' should have type 'approval_gate'"
                    )

    def test_sop_step_ids_are_unique(self, loaded_sops):
        """No two steps in the same SOP share an ID."""
        for sop_path, data in loaded_sops:
            steps = data.get("steps", [])
            ids = [s.get("id", "") for s in steps]
            seen = set()
            dupes = []
            for step_id in ids:
                if step_id in seen:
                    dupes.append(step_id)
                seen.add(step_id)
            assert not dupes, (
                f"{sop_path.name}: duplicate step IDs: {dupes}"
            )

    def test_sop_dependencies_reference_existing_steps(self, loaded_sops):
        """All depends_on references must point to valid step IDs within the SOP."""
        for sop_path, data in loaded_sops:
            steps = data.get("steps", [])
            valid_ids = {s["id"] for s in steps if "id" in s}
            for step in steps:
                deps = step.get("depends_on", [])
                for dep in deps:
                    assert dep in valid_ids, (
                        f"{sop_path.name}: step '{step['id']}' depends_on '{dep}' "
                        f"which does not exist. Valid IDs: {valid_ids}"
                    )


class TestSOPApprovalGates:
    """Test that SOPs include proper approval gates."""

    @pytest.fixture
    def loaded_sops(self):
        return [(f, _load_sop(f)) for f in _collect_sop_files()]

    def test_approval_gates_exist(self, loaded_sops):
        """Each SOP must have at least one approval gate."""
        for sop_path, data in loaded_sops:
            steps = data.get("steps", [])
            gates = [
                s for s in steps
                if s.get("type") == "approval_gate"
            ]
            assert len(gates) >= 1, (
                f"{sop_path.name}: no approval gates found. "
                f"Every SOP must have at least one human review point."
            )


class TestAdCampaignSOP:
    """Specific validation for the ad-campaign SOP."""

    @pytest.fixture
    def ad_campaign(self):
        path = PROJECT_ROOT / "sops" / "ad-campaign.yaml"
        assert path.exists(), "ad-campaign.yaml not found"
        return _load_sop(path)

    def test_ad_campaign_has_research_phase(self, ad_campaign):
        """Must have research-related steps."""
        steps = ad_campaign.get("steps", [])
        step_ids = [s["id"] for s in steps]
        research_steps = [sid for sid in step_ids if "research" in sid.lower() or "pain_point" in sid.lower() or "competitor" in sid.lower() or "hook" in sid.lower()]
        assert len(research_steps) >= 2, (
            f"Expected at least 2 research phase steps, found: {research_steps}"
        )

    def test_ad_campaign_has_generation_phase(self, ad_campaign):
        """Must have generation/production steps."""
        steps = ad_campaign.get("steps", [])
        step_ids = [s["id"] for s in steps]
        gen_steps = [sid for sid in step_ids if "generate" in sid.lower() or "build" in sid.lower() or "compose" in sid.lower()]
        assert len(gen_steps) >= 2, (
            f"Expected at least 2 generation phase steps, found: {gen_steps}"
        )

    def test_ad_campaign_has_two_approval_gates(self, ad_campaign):
        """The ad-campaign SOP should have both a research review and generation review."""
        steps = ad_campaign.get("steps", [])
        gates = [s for s in steps if s.get("type") == "approval_gate"]
        assert len(gates) >= 2, (
            f"Expected at least 2 approval gates (research + generation), found {len(gates)}"
        )
        gate_ids = [g["id"] for g in gates]
        assert any("research" in gid for gid in gate_ids), (
            f"No research review gate found. Gate IDs: {gate_ids}"
        )
        assert any("generation" in gid for gid in gate_ids), (
            f"No generation review gate found. Gate IDs: {gate_ids}"
        )

    def test_ad_campaign_has_input_schema(self, ad_campaign):
        """Must define an input schema for form generation."""
        schema = ad_campaign.get("input_schema", {})
        assert len(schema) >= 3, (
            f"Expected at least 3 input fields, found {len(schema)}"
        )
        assert "product_name" in schema, "Missing product_name in input_schema"
        assert "target_audience" in schema, "Missing target_audience in input_schema"

    def test_ad_campaign_has_output_schema(self, ad_campaign):
        """Must define what it produces."""
        schema = ad_campaign.get("output_schema", {})
        assert len(schema) >= 3, (
            f"Expected at least 3 output fields, found {len(schema)}"
        )
