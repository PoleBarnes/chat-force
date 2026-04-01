"""Validate workspace configurations.

Tests cover:
  - BlackTie workspace directory structure and config
  - Workspace template exists for new customer onboarding
  - Config files have required fields
"""

from pathlib import Path

import yaml
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKSPACES_DIR = PROJECT_ROOT / "workspaces"


# =========================================================================
# BlackTie workspace tests
# =========================================================================


class TestBlackTieWorkspace:
    """Test the BlackTie workspace directory and config."""

    def test_blacktie_workspace_exists(self):
        """BlackTie workspace directory must exist."""
        ws_dir = WORKSPACES_DIR / "blacktie"
        assert ws_dir.is_dir(), "workspaces/blacktie/ does not exist"

    def test_blacktie_directory_structure(self):
        """BlackTie must have config.yaml, context.md, sops/, forms/."""
        ws_dir = WORKSPACES_DIR / "blacktie"
        expected_files = ["config.yaml", "context.md"]
        expected_dirs = ["sops", "forms"]

        for f in expected_files:
            path = ws_dir / f
            assert path.is_file(), f"workspaces/blacktie/{f} not found"

        for d in expected_dirs:
            path = ws_dir / d
            assert path.is_dir(), f"workspaces/blacktie/{d}/ not found"

    def test_blacktie_config_is_valid_yaml(self):
        """BlackTie config.yaml must parse without errors."""
        config_path = WORKSPACES_DIR / "blacktie" / "config.yaml"
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_blacktie_config_has_required_fields(self):
        """BlackTie config must have workspace, channels, skills, sops sections."""
        config_path = WORKSPACES_DIR / "blacktie" / "config.yaml"
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))

        assert "workspace" in data, "Missing 'workspace' section"
        ws = data["workspace"]
        assert ws.get("id") == "blacktie"
        assert ws.get("name"), "Workspace name is empty"
        assert ws.get("tier") is not None, "Workspace tier not specified"
        assert ws.get("timezone"), "Workspace timezone not specified"

    def test_blacktie_config_has_channels(self):
        """BlackTie should have channel configuration."""
        config_path = WORKSPACES_DIR / "blacktie" / "config.yaml"
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        channels = data.get("channels", {})
        assert len(channels) >= 3, (
            f"Expected at least 3 channel configs, found {len(channels)}"
        )

    def test_blacktie_config_has_skills(self):
        """BlackTie should have enabled skills."""
        config_path = WORKSPACES_DIR / "blacktie" / "config.yaml"
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        skills = data.get("skills", [])
        assert len(skills) >= 3, (
            f"Expected at least 3 enabled skills, found {len(skills)}"
        )

    def test_blacktie_config_has_sops(self):
        """BlackTie should have enabled SOPs."""
        config_path = WORKSPACES_DIR / "blacktie" / "config.yaml"
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        sops = data.get("sops", [])
        assert len(sops) >= 3, (
            f"Expected at least 3 enabled SOPs, found {len(sops)}"
        )
        assert "ad-campaign" in sops

    def test_blacktie_config_has_heartbeat(self):
        """BlackTie should have heartbeat configuration."""
        config_path = WORKSPACES_DIR / "blacktie" / "config.yaml"
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        hb = data.get("heartbeat", {})
        assert hb.get("enabled") is True

    def test_blacktie_context_is_present(self):
        """context.md must exist and have substantial content."""
        ctx_path = WORKSPACES_DIR / "blacktie" / "context.md"
        content = ctx_path.read_text(encoding="utf-8")
        assert len(content) > 200, (
            f"context.md is too short ({len(content)} chars)"
        )
        assert "BlackTie" in content

    def test_blacktie_context_has_brand_info(self):
        """context.md should include brand/company information."""
        ctx_path = WORKSPACES_DIR / "blacktie" / "context.md"
        content = ctx_path.read_text(encoding="utf-8").lower()
        assert "post-frame" in content or "pole barn" in content, (
            "context.md should mention the business type"
        )
        assert "audience" in content or "target" in content, (
            "context.md should describe target audiences"
        )

    def test_blacktie_has_sop_files(self):
        """BlackTie must have at least 3 SOP files."""
        sops_dir = WORKSPACES_DIR / "blacktie" / "sops"
        sop_files = list(sops_dir.glob("*.yaml"))
        assert len(sop_files) >= 3, (
            f"Expected at least 3 SOP files, found {len(sop_files)}"
        )

    def test_blacktie_improvement_log_exists(self):
        """BlackTie should have an improvement log."""
        log_path = WORKSPACES_DIR / "blacktie" / "improvement-log.md"
        assert log_path.is_file(), "workspaces/blacktie/improvement-log.md not found"


# =========================================================================
# Workspace template tests
# =========================================================================


class TestWorkspaceTemplate:
    """Test the workspace template for new customer onboarding."""

    def test_template_directory_exists(self):
        """The _template workspace must exist."""
        template_dir = WORKSPACES_DIR / "_template"
        assert template_dir.is_dir(), "workspaces/_template/ does not exist"

    def test_template_has_config(self):
        """Template must have a config.yaml file."""
        config_path = WORKSPACES_DIR / "_template" / "config.yaml"
        assert config_path.is_file(), "workspaces/_template/config.yaml not found"

    def test_template_config_is_valid_yaml(self):
        """Template config must parse without errors."""
        config_path = WORKSPACES_DIR / "_template" / "config.yaml"
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "workspace" in data

    def test_template_has_context_md(self):
        """Template must have a context.md placeholder."""
        ctx_path = WORKSPACES_DIR / "_template" / "context.md"
        assert ctx_path.is_file(), "workspaces/_template/context.md not found"

    def test_template_has_subdirectories(self):
        """Template must have sops/, forms/, and skills/ directories."""
        template_dir = WORKSPACES_DIR / "_template"
        for subdir in ["sops", "forms", "skills"]:
            path = template_dir / subdir
            assert path.is_dir(), (
                f"workspaces/_template/{subdir}/ not found"
            )

    def test_template_config_has_placeholder_fields(self):
        """Template config should have empty/placeholder workspace fields."""
        config_path = WORKSPACES_DIR / "_template" / "config.yaml"
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        ws = data.get("workspace", {})
        # Template should have the id field (possibly empty placeholder)
        assert "id" in ws, "Template config missing workspace.id"
        assert "name" in ws, "Template config missing workspace.name"
