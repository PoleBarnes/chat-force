"""SOP-driven graph generator.

Reads a YAML SOP definition and dynamically generates a LangGraph workflow
from it. Each SOP encodes a repeatable process as a sequence of steps with
inputs, outputs, specialist assignments, and approval gates.

Example SOP YAML structure:

    name: blog-post-creation
    version: 1
    description: Create a blog post from a topic brief.
    input_schema:
      topic: { type: string, required: true }
      tone: { type: string, default: "professional" }
    steps:
      - id: research
        specialist: researcher
        description: Gather background material on the topic.
      - id: draft
        specialist: writer
        depends_on: [research]
        description: Write the first draft.
      - id: review
        type: approval_gate
        description: Human reviews the draft.
      - id: polish
        specialist: editor
        depends_on: [draft]
        description: Final polish and formatting.
    output_schema:
      document: { type: string }
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from ..nodes.agents import dispatch as agent_dispatch
from ..nodes.llm import call_claude, get_temperature
from ..nodes.sop_loader import SOPDefinition, SOPStep, load_sop_from_path
from ..nodes.specialists import get_specialist_prompt, SPECIALIST_PROMPTS
from ..nodes.utils import PROJECT_ROOT

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SOP graph state
# ---------------------------------------------------------------------------

class SOPGraphState(BaseModel):
    """State that flows through an SOP-generated graph."""
    sop_name: str = ""
    inputs: dict[str, Any] = Field(default_factory=dict)
    step_results: dict[str, Any] = Field(default_factory=dict)
    current_step: str = ""
    approved: bool = False
    outputs: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Node factory
# ---------------------------------------------------------------------------

def _make_task_node(step: SOPStep, sop: SOPDefinition):
    """Create a task node function for a given SOP step.

    The generated node calls Claude with specialist-appropriate system prompts,
    injects results from dependent steps, and stores the output.
    """

    def node_fn(state: SOPGraphState) -> dict[str, Any]:
        errors: list[str] = list(state.errors)

        # Gather results from dependencies
        dependency_context = ""
        for dep_id in step.depends_on:
            dep_result = state.step_results.get(dep_id, {})
            dep_output = dep_result.get("output", "")
            if dep_output:
                dependency_context += f"\n\n### Results from '{dep_id}':\n{dep_output}"

        # Build the specialist prompt
        specialist = step.specialist or "general"
        system_prompt = get_specialist_prompt(specialist)

        # Build the task prompt with SOP context
        inputs_text = ""
        if state.inputs:
            inputs_lines = [f"- {k}: {v}" for k, v in state.inputs.items()]
            inputs_text = "\n".join(inputs_lines)

        task_prompt = f"""Execute this step in the "{sop.name}" workflow.

## SOP: {sop.name}
{sop.description}

## Current Step: {step.id}
{step.description}

## Inputs
{inputs_text if inputs_text else "No specific inputs provided."}
{dependency_context if dependency_context else ""}

Produce a thorough, complete deliverable for this step. Be specific and actionable."""

        try:
            # H9: Use agent dispatch interface to route to the appropriate agent
            # H8: Temperature is handled inside the agent dispatcher
            agent_name = step.agent or "openclaw"
            output = agent_dispatch(
                agent=agent_name,
                prompt=task_prompt,
                system=system_prompt,
                specialist=specialist,
            )

            new_results = {
                **state.step_results,
                step.id: {"status": "completed", "output": output},
            }
        except Exception as exc:
            error_msg = f"SOP step '{step.id}' failed: {exc}"
            logger.error(error_msg)
            errors.append(error_msg)
            new_results = {
                **state.step_results,
                step.id: {"status": "error", "error": str(exc)},
            }

        return {
            "current_step": step.id,
            "step_results": new_results,
            "errors": errors,
        }

    node_fn.__name__ = f"sop_step_{step.id}"
    node_fn.__doc__ = step.description
    return node_fn


def _make_approval_node(step: SOPStep):
    """Create an approval-gate node for a given SOP step.

    The graph interrupts before this node, giving the interface layer time
    to render the current state and collect human feedback. When the graph
    resumes, the ``approved`` field in state reflects the human's decision.
    """

    def node_fn(state: SOPGraphState) -> dict[str, Any]:
        # Build a summary of work completed so far for the approval message
        completed_steps = {
            k: v for k, v in state.step_results.items()
            if isinstance(v, dict) and v.get("status") == "completed"
        }

        approval_context = {
            "gate_id": step.id,
            "gate_description": step.description,
            "completed_steps": list(completed_steps.keys()),
            "step_previews": {
                k: v.get("output", "")[:500]
                for k, v in completed_steps.items()
            },
        }

        return {
            "current_step": step.id,
            "approved": state.approved,
            "outputs": {**state.outputs, "approval_context": approval_context},
        }

    node_fn.__name__ = f"sop_gate_{step.id}"
    node_fn.__doc__ = f"Approval gate: {step.description}"
    return node_fn


# ---------------------------------------------------------------------------
# Graph generator
# ---------------------------------------------------------------------------

def _approval_gate_router(state: SOPGraphState) -> str:
    """Route after an approval gate: continue if approved, END if rejected."""
    if state.approved:
        return "continue"
    return "end"


def generate_graph_from_sop(sop: SOPDefinition) -> tuple[StateGraph, list[str]]:
    """Dynamically build a LangGraph StateGraph from an SOP definition.

    Builds a proper DAG from the ``depends_on`` declarations on each step,
    enabling parallel execution of independent steps (e.g. the three research
    streams in the ad-campaign SOP all depend on ``parse_brief`` and can run
    concurrently).

    Wiring rules:
    1. Steps with explicit ``depends_on`` get edges FROM each dependency.
    2. Steps with no ``depends_on`` (except the very first step) implicitly
       depend on the previous step in declaration order — this preserves
       backward compatibility for SOPs that don't use depends_on at all.
    3. Steps with no downstream dependents (terminal nodes) edge to END.
    4. Approval gates get conditional edges: approved -> first downstream
       dependent (or END), rejected -> END.

    Parameters
    ----------
    sop:
        The parsed SOP definition.

    Returns
    -------
    tuple[StateGraph, list[str]]
        The constructed (but not compiled) graph builder and a list of
        approval gate node IDs for interrupt configuration.
    """
    builder = StateGraph(SOPGraphState)
    approval_gate_ids: list[str] = []

    if not sop.steps:
        return builder, approval_gate_ids

    # Index steps by ID for quick lookup
    step_by_id: dict[str, SOPStep] = {step.id: step for step in sop.steps}

    # ------------------------------------------------------------------
    # 1. Add all nodes
    # ------------------------------------------------------------------
    for step in sop.steps:
        if step.type == "approval_gate":
            builder.add_node(step.id, _make_approval_node(step))
            approval_gate_ids.append(step.id)
        else:
            builder.add_node(step.id, _make_task_node(step, sop))

    # ------------------------------------------------------------------
    # 2. Set entry point
    # ------------------------------------------------------------------
    builder.set_entry_point(sop.steps[0].id)

    # ------------------------------------------------------------------
    # 3. Resolve effective dependencies for every step
    # ------------------------------------------------------------------
    # effective_deps[step_id] = set of step IDs this step depends on
    effective_deps: dict[str, set[str]] = {}
    has_explicit_deps: set[str] = set()

    for step in sop.steps:
        if step.depends_on:
            effective_deps[step.id] = set(step.depends_on)
            has_explicit_deps.add(step.id)
        else:
            effective_deps[step.id] = set()

    # For steps with no explicit depends_on (except the first), create an
    # implicit dependency on the previous step to maintain sequential order.
    # This preserves backward compatibility for SOPs that omit depends_on.
    for i, step in enumerate(sop.steps):
        if i > 0 and step.id not in has_explicit_deps:
            prev_step = sop.steps[i - 1]
            effective_deps[step.id].add(prev_step.id)

    # ------------------------------------------------------------------
    # 4. Build the forward-edge map: dependents[A] = [B, C] means A -> B, A -> C
    # ------------------------------------------------------------------
    dependents: dict[str, list[str]] = {step.id: [] for step in sop.steps}

    for step in sop.steps:
        for dep_id in effective_deps[step.id]:
            if dep_id in dependents:
                dependents[dep_id].append(step.id)

    # ------------------------------------------------------------------
    # 5. Wire edges
    # ------------------------------------------------------------------
    for step in sop.steps:
        targets = dependents[step.id]

        if step.type == "approval_gate":
            # Approval gates use conditional routing:
            #   approved  -> all downstream targets (or END if terminal)
            #   rejected  -> END
            if targets:
                target_set = list(targets)

                if len(target_set) > 1:
                    # Multiple steps depend on this gate — fan-out to all
                    # when approved, END when rejected.
                    def _make_multi_gate_router(gate_targets: list[str]):
                        def _router(state: SOPGraphState) -> list[str]:
                            if state.approved:
                                return gate_targets
                            return [END]
                        return _router

                    builder.add_conditional_edges(
                        step.id,
                        _make_multi_gate_router(target_set),
                        # path_map: identity mapping so LangGraph knows all
                        # possible destinations for graph validation
                        {t: t for t in target_set + [END]},
                    )
                else:
                    # Single downstream step after the gate
                    def _make_gate_router(gate_target: str):
                        def _router(state: SOPGraphState) -> str:
                            if state.approved:
                                return "continue"
                            return "end"
                        return _router

                    builder.add_conditional_edges(
                        step.id,
                        _make_gate_router(target_set[0]),
                        {"continue": target_set[0], "end": END},
                    )
            else:
                # Terminal approval gate (last step) — always go to END
                builder.add_edge(step.id, END)
        else:
            # Normal task step
            if targets:
                for target in targets:
                    builder.add_edge(step.id, target)
            else:
                # Terminal step — no downstream consumers, go to END
                builder.add_edge(step.id, END)

    return builder, approval_gate_ids


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Cache for compiled SOP graphs to avoid re-parsing on repeated calls
_sop_graph_cache: dict[str, Any] = {}


def compile_sop_graph(sop_path: Union[str, Path]):
    """Load an SOP YAML and return a compiled, runnable LangGraph.

    Compiled graphs are cached by file path so repeated calls are fast.

    Parameters
    ----------
    sop_path:
        Path to the SOP YAML file.

    Returns
    -------
    CompiledGraph
        A compiled LangGraph ready for invocation.
    """
    cache_key = str(Path(sop_path).resolve())
    if cache_key in _sop_graph_cache:
        return _sop_graph_cache[cache_key]

    sop = load_sop_from_path(sop_path)
    builder, approval_gate_ids = generate_graph_from_sop(sop)
    compiled = builder.compile(
        interrupt_before=approval_gate_ids,
    )

    _sop_graph_cache[cache_key] = compiled
    return compiled


# ---------------------------------------------------------------------------
# Default graph -- used by LangGraph Cloud (langgraph.json points here)
# ---------------------------------------------------------------------------

# For the LangGraph Cloud entrypoint we expose a router graph that receives
# an SOP name, loads it, and delegates execution to the compiled SOP graph.

_router_builder = StateGraph(SOPGraphState)


def _router_entry(state: SOPGraphState) -> dict[str, Any]:
    """Router entry node for the SOP runner graph.

    Receives the SOP name from the main graph, loads and compiles the
    matching SOP YAML, and delegates execution to the compiled SOP graph.
    """
    if not state.sop_name:
        return {"errors": state.errors + ["No SOP name specified."]}

    # Search for the SOP file in known locations
    search_dirs = [
        PROJECT_ROOT / "sops",
    ]

    sop_path: Optional[Path] = None
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for yaml_file in search_dir.rglob("*.yaml"):
            try:
                raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and raw.get("name", "").lower() == state.sop_name.lower():
                    sop_path = yaml_file
                    break
            except (yaml.YAMLError, OSError):
                continue
        if sop_path:
            break

    if not sop_path:
        return {"errors": state.errors + [f"SOP '{state.sop_name}' not found."]}

    try:
        compiled_graph = compile_sop_graph(sop_path)
        result = compiled_graph.invoke(state.model_dump())
        return {
            "step_results": result.get("step_results", {}),
            "outputs": result.get("outputs", {}),
            "errors": result.get("errors", []),
        }
    except Exception as exc:
        logger.error("SOP execution failed: %s", exc)
        return {"errors": state.errors + [f"SOP execution error: {exc}"]}


_router_builder.add_node("entry", _router_entry)
_router_builder.set_entry_point("entry")
_router_builder.add_edge("entry", END)

graph = _router_builder.compile()
