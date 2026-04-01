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

from ..nodes.llm import call_claude

logger = logging.getLogger(__name__)

# Specialist system prompts (same as main graph for consistency)
_SPECIALIST_PROMPTS: dict[str, str] = {
    "researcher": (
        "You are a research specialist. Gather comprehensive, accurate information "
        "on the given topic. Cite sources where possible. Focus on facts, data, and "
        "actionable insights."
    ),
    "writer": (
        "You are a professional writer. Produce clear, engaging, well-structured "
        "content. Match the requested tone and audience."
    ),
    "editor": (
        "You are an editorial specialist. Polish content for grammar, clarity, "
        "consistency, and tone. Preserve the author's voice while improving readability."
    ),
    "analyst": (
        "You are a data analyst. Examine data or situations, identify patterns, "
        "and present findings in a clear, structured format."
    ),
    "strategist": (
        "You are a marketing/business strategist. Develop actionable strategies "
        "with specific, measurable recommendations."
    ),
    "developer": (
        "You are a software developer. Write clean, well-documented code following "
        "best practices. Include error handling."
    ),
    "openclaw": (
        "You are a capable AI assistant. Complete the assigned task thoroughly "
        "and accurately, applying best practices from the relevant domain."
    ),
    "general": (
        "You are a capable AI assistant. Complete the assigned task thoroughly "
        "and accurately, applying best practices from the relevant domain."
    ),
}


# ---------------------------------------------------------------------------
# SOP data model
# ---------------------------------------------------------------------------

class SOPStep(BaseModel):
    """A single step inside an SOP definition."""
    id: str
    description: str = ""
    specialist: str = ""
    type: str = "task"  # "task" or "approval_gate"
    depends_on: list[str] = Field(default_factory=list)


class SOPDefinition(BaseModel):
    """Parsed representation of an SOP YAML file."""
    name: str
    version: int = 1
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    steps: list[SOPStep] = Field(default_factory=list)
    output_schema: dict[str, Any] = Field(default_factory=dict)


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
# SOP loading
# ---------------------------------------------------------------------------

def load_sop(path: Union[str, Path]) -> SOPDefinition:
    """Load and validate an SOP from a YAML file.

    Parameters
    ----------
    path:
        Path to the SOP YAML file.

    Returns
    -------
    SOPDefinition
        Parsed and validated SOP definition.

    Raises
    ------
    FileNotFoundError
        If the YAML file does not exist.
    ValueError
        If the YAML is malformed or missing required fields.
    """
    sop_path = Path(path)
    if not sop_path.exists():
        raise FileNotFoundError(f"SOP file not found: {sop_path}")

    try:
        raw = yaml.safe_load(sop_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {sop_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"SOP file must contain a YAML mapping, got {type(raw).__name__}")

    if "name" not in raw:
        raise ValueError(f"SOP file {sop_path} is missing required field 'name'")

    # Normalize step definitions
    steps = raw.get("steps", [])
    normalized_steps = []
    for step_raw in steps:
        step_type = step_raw.get("type", "task")
        # Normalize "human_approval" to "approval_gate" for consistency
        if step_type == "human_approval":
            step_type = "approval_gate"
        normalized_steps.append(SOPStep(
            id=step_raw.get("id", ""),
            description=step_raw.get("description", ""),
            specialist=step_raw.get("specialist", step_raw.get("agent", "general")),
            type=step_type,
            depends_on=step_raw.get("depends_on", []),
        ))

    return SOPDefinition(
        name=raw["name"],
        version=raw.get("version", 1),
        description=raw.get("description", ""),
        input_schema=raw.get("input_schema", raw.get("inputs", {})),
        steps=normalized_steps,
        output_schema=raw.get("output_schema", {}),
    )


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
        system_prompt = _SPECIALIST_PROMPTS.get(
            specialist, _SPECIALIST_PROMPTS["general"]
        )

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
            # Use Sonnet for routine steps, Opus for complex specialist work
            model = "claude-sonnet-4-6"
            if specialist in ("strategist", "analyst", "developer"):
                model = "claude-opus-4-6"

            output = call_claude(
                prompt=task_prompt,
                system=system_prompt,
                model=model,
                temperature=0.0,
                max_tokens=4096,
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

def generate_graph_from_sop(sop: SOPDefinition) -> tuple[StateGraph, list[str]]:
    """Dynamically build a LangGraph StateGraph from an SOP definition.

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

    # Create nodes for every step
    for step in sop.steps:
        if step.type == "approval_gate":
            builder.add_node(step.id, _make_approval_node(step))
            approval_gate_ids.append(step.id)
        else:
            builder.add_node(step.id, _make_task_node(step, sop))

    # Wire edges based on dependency order
    if sop.steps:
        builder.set_entry_point(sop.steps[0].id)

        for i, step in enumerate(sop.steps):
            if i < len(sop.steps) - 1:
                next_step = sop.steps[i + 1]
                builder.add_edge(step.id, next_step.id)
            else:
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

    sop = load_sop(sop_path)
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
    _project_root = Path(__file__).resolve().parent.parent.parent
    search_dirs = [
        _project_root / "workspaces",
        _project_root / "platform" / "sops",
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
