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

from pathlib import Path
from typing import Any

import yaml
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field


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

def load_sop(path: str | Path) -> SOPDefinition:
    """Load and validate an SOP from a YAML file.

    TODO: Implement the following:
      - Validate against a JSON Schema for SOP definitions
      - Resolve relative paths for any referenced templates or tools
      - Support SOP inheritance / composition (base SOP + overrides)
    """
    raw = yaml.safe_load(Path(path).read_text())
    return SOPDefinition(**raw)


# ---------------------------------------------------------------------------
# Node factory
# ---------------------------------------------------------------------------

def _make_task_node(step: SOPStep):
    """Create a task node function for a given SOP step.

    TODO: Implement the following:
      - Dispatch to the specialist identified in step.specialist
      - Inject results from dependent steps (step.depends_on) into the call
      - Use Claude (Opus for complex, Sonnet for routine) as the LLM backend
      - Capture and store the result in step_results[step.id]
    """

    def node_fn(state: SOPGraphState) -> dict[str, Any]:
        return {
            "current_step": step.id,
            "step_results": {
                **state.step_results,
                step.id: {"status": "completed", "output": f"placeholder for {step.id}"},
            },
        }

    node_fn.__name__ = f"sop_step_{step.id}"
    node_fn.__doc__ = step.description
    return node_fn


def _make_approval_node(step: SOPStep):
    """Create an approval-gate node for a given SOP step.

    TODO: Implement the following:
      - Format the current deliverables for human review
      - The graph will interrupt before this node (see graph assembly)
      - On resume, check the human's decision (approve / reject / edit)
      - Route accordingly
    """

    def node_fn(state: SOPGraphState) -> dict[str, Any]:
        return {
            "current_step": step.id,
            "approved": True,
        }

    node_fn.__name__ = f"sop_gate_{step.id}"
    node_fn.__doc__ = f"Approval gate: {step.description}"
    return node_fn


# ---------------------------------------------------------------------------
# Graph generator
# ---------------------------------------------------------------------------

def generate_graph_from_sop(sop: SOPDefinition) -> StateGraph:
    """Dynamically build a LangGraph StateGraph from an SOP definition.

    TODO: Implement the following:
      - Detect parallelisable steps (independent deps) and fan out
      - Add error-handling / retry edges
      - Wire up specialist tool bindings per step
      - Add a finalization node that assembles outputs per output_schema
    """
    builder = StateGraph(SOPGraphState)
    approval_gate_ids: list[str] = []

    # Create nodes for every step
    for step in sop.steps:
        if step.type == "approval_gate":
            builder.add_node(step.id, _make_approval_node(step))
            approval_gate_ids.append(step.id)
        else:
            builder.add_node(step.id, _make_task_node(step))

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

def compile_sop_graph(sop_path: str | Path):
    """Load an SOP YAML and return a compiled, runnable LangGraph.

    TODO: Implement the following:
      - Cache compiled graphs so repeated calls are fast
      - Validate SOP input_schema against provided inputs at runtime
      - Attach LangSmith tracing metadata (sop_name, version)
    """
    sop = load_sop(sop_path)
    builder, approval_gate_ids = generate_graph_from_sop(sop)
    return builder.compile(
        interrupt_before=approval_gate_ids,
    )


# ---------------------------------------------------------------------------
# Default graph — used by LangGraph Cloud (langgraph.json points here)
# ---------------------------------------------------------------------------

# For the LangGraph Cloud entrypoint we expose a minimal placeholder graph.
# In production this would be replaced by a router that selects the right
# SOP graph at runtime.

_placeholder_builder = StateGraph(SOPGraphState)


def _placeholder_entry(state: SOPGraphState) -> dict[str, Any]:
    """Placeholder entry node for the SOP runner graph.

    TODO: Replace with a router that:
      - Receives the SOP name from the main graph
      - Loads and compiles the matching SOP YAML
      - Delegates execution to the compiled SOP graph
    """
    return {"errors": ["No SOP specified — this is a placeholder graph."]}


_placeholder_builder.add_node("entry", _placeholder_entry)
_placeholder_builder.set_entry_point("entry")
_placeholder_builder.add_edge("entry", END)

graph = _placeholder_builder.compile()
