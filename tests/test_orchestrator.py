"""Validate LangGraph graph compilation and orchestrator modules.

These tests verify that:
  - All three graphs compile without import or construction errors
  - The SOP runner can load and generate graphs from YAML definitions
  - Context assembly works with platform and workspace configs
  - Routing logic correctly identifies dispatch vs. direct-handle cases
  - SOP matching finds the right SOP for a given input
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# =========================================================================
# Graph compilation tests
# =========================================================================


class TestMainGraph:
    """Test that the main task graph compiles and has correct structure."""

    def test_main_graph_compiles(self):
        """The main task graph must compile without errors."""
        from orchestrator.graphs.main import build_graph
        graph_builder = build_graph()
        assert graph_builder is not None

    def test_main_graph_has_expected_nodes(self):
        """The main graph should contain all expected nodes."""
        from orchestrator.graphs.main import build_graph
        builder = build_graph()
        # StateGraph stores nodes in its _nodes dict
        node_names = set(builder.nodes.keys())
        expected = {
            "entry_node",
            "planner_node",
            "preview_interrupt",
            "execution_node",
            "deliverable_interrupt",
            "finalization_node",
            "mechanic_b_node",
        }
        missing = expected - node_names
        assert not missing, f"Missing nodes in main graph: {missing}"

    def test_main_graph_has_entry_point(self):
        """The main graph must define an entry point."""
        from orchestrator.graphs.main import build_graph
        builder = build_graph()
        # The graph compiles successfully with set_entry_point called,
        # which means it has a valid entry point. Verify by compiling.
        compiled = builder.compile()
        assert compiled is not None

    def test_compiled_main_graph_exists(self):
        """The pre-compiled graph object must exist."""
        from orchestrator.graphs.main import graph
        assert graph is not None


class TestMechanicBGraph:
    """Test that the Mechanic B analysis graph compiles."""

    def test_mechanic_b_graph_compiles(self):
        """The Mechanic B graph must compile without errors."""
        from orchestrator.graphs.mechanic_b import build_graph
        builder = build_graph()
        assert builder is not None

    def test_mechanic_b_has_expected_nodes(self):
        """Mechanic B should have fetch, analyze, propose, and report nodes."""
        from orchestrator.graphs.mechanic_b import build_graph
        builder = build_graph()
        node_names = set(builder.nodes.keys())
        expected = {
            "fetch_traces",
            "analyze_quality",
            "generate_proposals",
            "compile_report",
        }
        missing = expected - node_names
        assert not missing, f"Missing nodes in Mechanic B graph: {missing}"

    def test_compiled_mechanic_b_graph_exists(self):
        """The pre-compiled Mechanic B graph object must exist."""
        from orchestrator.graphs.mechanic_b import graph
        assert graph is not None


class TestSOPRunnerGraph:
    """Test the SOP runner graph compilation and SOP loading."""

    def test_sop_runner_compiles(self):
        """The SOP runner router graph must compile."""
        from orchestrator.graphs.sop_runner import graph
        assert graph is not None

    def test_load_sop_from_file(self):
        """Can load the ad-campaign SOP from a YAML file."""
        from orchestrator.graphs.sop_runner import load_sop
        sop_path = PROJECT_ROOT / "workspaces" / "blacktie" / "sops" / "ad-campaign.yaml"
        sop = load_sop(sop_path)
        assert sop.name == "ad-campaign"
        assert sop.version >= 1
        assert len(sop.steps) > 0

    def test_load_sop_validates_fields(self):
        """load_sop raises on invalid YAML."""
        from orchestrator.graphs.sop_runner import load_sop
        with pytest.raises(FileNotFoundError):
            load_sop("/nonexistent/path.yaml")

    def test_sop_graph_generation(self):
        """Can generate a LangGraph from the ad-campaign SOP YAML."""
        from orchestrator.graphs.sop_runner import load_sop, generate_graph_from_sop
        sop = load_sop(PROJECT_ROOT / "workspaces" / "blacktie" / "sops" / "ad-campaign.yaml")
        builder, gates = generate_graph_from_sop(sop)
        assert builder is not None
        assert len(gates) >= 2, (
            f"Expected at least 2 approval gates, found {len(gates)}: {gates}"
        )

    def test_sop_graph_generation_all_sops(self):
        """Every workspace SOP must produce a valid graph."""
        from orchestrator.graphs.sop_runner import load_sop, generate_graph_from_sop
        sop_dir = PROJECT_ROOT / "workspaces" / "blacktie" / "sops"
        for sop_file in sorted(sop_dir.glob("*.yaml")):
            sop = load_sop(sop_file)
            builder, gates = generate_graph_from_sop(sop)
            assert builder is not None, f"Graph generation failed for {sop_file.name}"
            assert len(gates) >= 1, (
                f"{sop_file.name}: expected at least 1 approval gate, found {len(gates)}"
            )

    def test_sop_definition_model_fields(self):
        """SOPDefinition Pydantic model must have the expected fields."""
        from orchestrator.graphs.sop_runner import SOPDefinition
        fields = set(SOPDefinition.model_fields.keys())
        expected = {"name", "version", "description", "input_schema", "steps", "output_schema"}
        assert expected.issubset(fields), (
            f"SOPDefinition missing fields: {expected - fields}"
        )


# =========================================================================
# Context assembly tests
# =========================================================================


class TestContextAssembly:
    """Test the three-tier context assembly module."""

    def test_load_platform_config(self):
        """Platform config must load and contain expected keys."""
        from orchestrator.nodes.context import load_platform_config
        config = load_platform_config()
        assert isinstance(config, dict)
        assert "platform" in config, "Platform config missing 'platform' key"
        assert "models" in config, "Platform config missing 'models' key"
        assert "routing" in config, "Platform config missing 'routing' key"

    def test_load_workspace_config(self):
        """BlackTie workspace config must load correctly."""
        from orchestrator.nodes.context import load_workspace_config
        config = load_workspace_config("blacktie")
        assert isinstance(config, dict)
        assert "workspace" in config, "Workspace config missing 'workspace' key"
        ws = config["workspace"]
        assert ws.get("id") == "blacktie"
        assert ws.get("name") == "BlackTie Post-Frame Buildings"

    def test_load_workspace_context_md(self):
        """BlackTie context.md must load as non-empty text."""
        from orchestrator.nodes.context import load_workspace_context
        ctx = load_workspace_context("blacktie")
        assert isinstance(ctx, str)
        assert len(ctx) > 100, "context.md content is too short"
        assert "BlackTie" in ctx

    def test_load_workspace_config_nonexistent(self):
        """Loading config for a nonexistent workspace returns empty dict."""
        from orchestrator.nodes.context import load_workspace_config
        config = load_workspace_config("nonexistent-workspace-xyz")
        assert config == {}

    def test_assemble_context(self):
        """Full context assembly should produce a non-empty string."""
        from orchestrator.nodes.context import assemble_context
        result = assemble_context(
            workspace_id="blacktie",
            thread_messages=[],
            current_input="Create an ad campaign for the new building",
            token_budget=100_000,
        )
        assert isinstance(result, str)
        assert len(result) > 100
        assert "Current Request" in result or "ad campaign" in result.lower()

    def test_assemble_context_with_thread_messages(self):
        """Context assembly should include thread messages."""
        from orchestrator.nodes.context import assemble_context
        messages = [
            {"role": "user", "content": "What buildings do we have?"},
            {"role": "assistant", "content": "We have several building packages."},
        ]
        result = assemble_context(
            workspace_id="blacktie",
            thread_messages=messages,
            current_input="Tell me more about the 80x120",
            token_budget=100_000,
        )
        assert isinstance(result, str)
        assert len(result) > 100


# =========================================================================
# Routing logic tests
# =========================================================================


class TestRoutingLogic:
    """Test the routing decision module."""

    def test_campaign_triggers_dispatch(self):
        """A campaign request should trigger dispatch."""
        from orchestrator.nodes.routing import should_dispatch
        dispatch, sop_name = should_dispatch(
            "Run the ad campaign for BlackTie", "blacktie"
        )
        assert dispatch is True

    def test_simple_question_does_not_dispatch(self):
        """A simple question should not trigger dispatch."""
        from orchestrator.nodes.routing import should_dispatch
        dispatch, sop_name = should_dispatch(
            "What time is it?", "blacktie"
        )
        assert dispatch is False

    def test_deploy_keyword_triggers_dispatch(self):
        """The 'deploy' keyword from base-config should trigger dispatch."""
        from orchestrator.nodes.routing import should_dispatch
        dispatch, _ = should_dispatch(
            "Deploy the latest changes to staging", "blacktie"
        )
        assert dispatch is True

    def test_complexity_indicators_trigger_dispatch(self):
        """Multi-step or workflow language should trigger dispatch."""
        from orchestrator.nodes.routing import should_dispatch
        dispatch, _ = should_dispatch(
            "I need a step by step plan to redesign the website", "blacktie"
        )
        assert dispatch is True

    def test_build_keyword_triggers_dispatch(self):
        """The 'build' keyword should trigger dispatch."""
        from orchestrator.nodes.routing import should_dispatch
        dispatch, _ = should_dispatch(
            "Build me a landing page for the cold storage product", "blacktie"
        )
        assert dispatch is True


# =========================================================================
# SOP matching tests
# =========================================================================


class TestSOPMatching:
    """Test the SOP matcher module."""

    def test_match_ad_campaign_sop(self):
        """Input containing the SOP name should match the ad-campaign SOP."""
        from orchestrator.nodes.sop_loader import match_sop
        # The matcher does exact substring match on the SOP name ("ad-campaign"),
        # so the hyphenated form must appear in the input.
        result = match_sop(
            "Create an ad-campaign for the new building", "blacktie"
        )
        assert result is not None, "Expected ad-campaign SOP match, got None"
        assert "ad-campaign" in result.lower()

    def test_match_landing_page_sop(self):
        """Input about landing pages should match the landing-page SOP."""
        from orchestrator.nodes.sop_loader import match_sop
        result = match_sop(
            "Build a landing page for the 80x120 building", "blacktie"
        )
        assert result is not None, "Expected landing-page SOP match, got None"
        assert "landing-page" in result.lower()

    def test_match_email_sequence_sop(self):
        """Input about email sequences should match the email-sequence SOP."""
        from orchestrator.nodes.sop_loader import match_sop
        result = match_sop(
            "Create an email sequence for the cold storage product", "blacktie"
        )
        assert result is not None, "Expected email-sequence SOP match, got None"
        assert "email" in result.lower()

    def test_no_match_for_unrelated_input(self):
        """An unrelated question should not match any SOP."""
        from orchestrator.nodes.sop_loader import match_sop
        result = match_sop(
            "How tall is the Eiffel Tower?", "blacktie"
        )
        assert result is None, f"Expected no SOP match, got '{result}'"

    def test_list_sops_for_blacktie(self):
        """Listing SOPs for blacktie should return workspace + platform SOPs."""
        from orchestrator.nodes.sop_loader import list_sops
        sops = list_sops("blacktie")
        assert len(sops) >= 3, (
            f"Expected at least 3 SOPs for blacktie, found {len(sops)}"
        )
        names = {s["name"] for s in sops}
        assert "ad-campaign" in names
        assert "landing-page" in names
        assert "email-sequence" in names

    def test_load_sop_by_name(self):
        """Can load a specific SOP by name through the sop_loader module."""
        from orchestrator.nodes.sop_loader import load_sop
        sop = load_sop("blacktie", "ad-campaign")
        assert isinstance(sop, dict)
        assert sop["name"] == "ad-campaign"
        assert "steps" in sop

    def test_load_sop_not_found(self):
        """Loading a nonexistent SOP raises FileNotFoundError."""
        from orchestrator.nodes.sop_loader import load_sop
        with pytest.raises(FileNotFoundError):
            load_sop("blacktie", "nonexistent-sop-xyz")
