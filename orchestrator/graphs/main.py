"""Main task graph for the Digital Workforce Platform orchestrator.

This graph handles the full lifecycle of a user task:
  1. Parse input and match to an SOP
  2. Plan the task breakdown
  3. Present the plan for human approval (interrupt)
  4. Execute specialist work (parallel or sequential)
  5. Present deliverables for human review (interrupt)
  6. Package final outputs
  7. Run Mechanic B analysis on the execution
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------

class TaskStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    AWAITING_PLAN_APPROVAL = "awaiting_plan_approval"
    EXECUTING = "executing"
    AWAITING_DELIVERABLE_REVIEW = "awaiting_deliverable_review"
    FINALIZING = "finalizing"
    ANALYZING = "analyzing"
    COMPLETE = "complete"


class TaskStep(BaseModel):
    """A single step inside a planned task breakdown."""
    id: str
    description: str
    specialist: str = ""
    depends_on: list[str] = Field(default_factory=list)
    result: Any = None


class GraphState(BaseModel):
    """Typed state that flows through every node in the main graph."""

    # -- Input --
    raw_input: str = ""
    thread_id: str = ""
    workspace_id: str = ""

    # -- Context --
    matched_sop: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)

    # -- Planning --
    plan: list[TaskStep] = Field(default_factory=list)
    plan_approved: bool = False

    # -- Execution --
    execution_results: dict[str, Any] = Field(default_factory=dict)
    deliverables: list[dict[str, Any]] = Field(default_factory=list)

    # -- Review --
    deliverables_approved: bool = False

    # -- Output --
    final_output: dict[str, Any] = Field(default_factory=dict)

    # -- Mechanic B --
    mechanic_b_report: dict[str, Any] = Field(default_factory=dict)

    # -- Meta --
    status: TaskStatus = TaskStatus.PENDING
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Node implementations (placeholders)
# ---------------------------------------------------------------------------

def entry_node(state: GraphState) -> dict[str, Any]:
    """Parse the user's input, load workspace/thread context, and match an SOP.

    TODO: Implement the following:
      - Fetch thread history from the interface layer
      - Assemble context (Platform -> Workspace -> Thread -> Current input)
      - Match input against registered SOPs (exact match, then fuzzy)
      - If an SOP matches, set matched_sop so planner_node can use it
      - Apply token-budget truncation for context
    """
    return {
        "status": TaskStatus.PLANNING,
        "context": {"source": "placeholder"},
        "matched_sop": None,
    }


def planner_node(state: GraphState) -> dict[str, Any]:
    """Create a task breakdown (plan) for the incoming request.

    TODO: Implement the following:
      - If an SOP was matched, load its YAML and generate steps from it
      - Otherwise, use Claude (Opus for complex, Sonnet for routine) to
        decompose the task into ordered steps with specialist assignments
      - Identify parallelisable steps via dependency analysis
      - Produce a list[TaskStep] representing the plan
    """
    placeholder_plan = [
        TaskStep(id="step-1", description="Placeholder step", specialist="general"),
    ]
    return {
        "status": TaskStatus.AWAITING_PLAN_APPROVAL,
        "plan": placeholder_plan,
    }


def preview_interrupt(state: GraphState) -> dict[str, Any]:
    """Show the plan to the human and wait for approval.

    This node is configured with interrupt_before so the graph pauses
    *before* entering it, giving the interface layer time to render the
    plan and collect Approve / Reject / Edit feedback.

    TODO: Implement the following:
      - Format the plan into a rich Slack Block Kit / Google Chat Card message
      - On rejection, route back to planner_node with feedback
      - On edit, merge edits into the plan and re-present
    """
    return {
        "plan_approved": True,
        "status": TaskStatus.EXECUTING,
    }


def execution_node(state: GraphState) -> dict[str, Any]:
    """Execute the approved plan — fan out to specialists.

    TODO: Implement the following:
      - For each step in the plan, dispatch to the appropriate specialist
        sub-graph or tool
      - Run independent steps in parallel (LangGraph Send API)
      - Run dependent steps sequentially, injecting prior results
      - Collect results and surface any errors
      - Checkpoint after every step (LangGraph handles this automatically)
    """
    results: dict[str, Any] = {}
    deliverables: list[dict[str, Any]] = []
    for step in state.plan:
        results[step.id] = {"status": "completed", "output": "placeholder"}
        deliverables.append({"step_id": step.id, "content": "placeholder deliverable"})

    return {
        "execution_results": results,
        "deliverables": deliverables,
        "status": TaskStatus.AWAITING_DELIVERABLE_REVIEW,
    }


def deliverable_interrupt(state: GraphState) -> dict[str, Any]:
    """Show deliverables to the human for review.

    This node is configured with interrupt_before so the graph pauses
    *before* entering it, letting the interface layer present deliverables
    and collect Approve / Reject / Re-run feedback.

    TODO: Implement the following:
      - Format deliverables into reviewable messages
      - On rejection, route back to execution_node with feedback
      - On re-run, allow selective step re-execution
    """
    return {
        "deliverables_approved": True,
        "status": TaskStatus.FINALIZING,
    }


def finalization_node(state: GraphState) -> dict[str, Any]:
    """Package outputs into the final deliverable set.

    TODO: Implement the following:
      - Aggregate deliverables into the expected output format
      - Generate any summary artifacts (reports, files, links)
      - Post final output to the originating thread via the interface layer
      - Update workspace memory with task outcome
    """
    return {
        "final_output": {
            "summary": "Task completed successfully (placeholder)",
            "deliverables": state.deliverables,
        },
        "status": TaskStatus.ANALYZING,
    }


def mechanic_b_node(state: GraphState) -> dict[str, Any]:
    """Analyze the execution using Mechanic B.

    This node invokes the Mechanic B sub-graph to review LangSmith traces
    for the current run and produce improvement proposals.

    TODO: Implement the following:
      - Collect the LangSmith run/trace ID for this graph execution
      - Invoke the mechanic_b sub-graph with trace data
      - Post the Mechanic B report to the admin approvals channel
      - Include Approve / Reject buttons for each proposal
    """
    return {
        "mechanic_b_report": {
            "score": 0.0,
            "proposals": [],
            "summary": "Mechanic B analysis placeholder",
        },
        "status": TaskStatus.COMPLETE,
    }


# ---------------------------------------------------------------------------
# Routing helpers
# ---------------------------------------------------------------------------

def after_preview(state: GraphState) -> str:
    """Route after the plan preview interrupt.

    TODO: Handle rejection -> route back to planner_node.
    """
    if state.plan_approved:
        return "execution_node"
    return "planner_node"


def after_deliverable_review(state: GraphState) -> str:
    """Route after the deliverable review interrupt.

    TODO: Handle rejection -> route back to execution_node.
    """
    if state.deliverables_approved:
        return "finalization_node"
    return "execution_node"


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    """Construct and compile the main task graph."""

    builder = StateGraph(GraphState)

    # -- Add nodes --
    builder.add_node("entry_node", entry_node)
    builder.add_node("planner_node", planner_node)
    builder.add_node("preview_interrupt", preview_interrupt)
    builder.add_node("execution_node", execution_node)
    builder.add_node("deliverable_interrupt", deliverable_interrupt)
    builder.add_node("finalization_node", finalization_node)
    builder.add_node("mechanic_b_node", mechanic_b_node)

    # -- Set entry point --
    builder.set_entry_point("entry_node")

    # -- Add edges --
    builder.add_edge("entry_node", "planner_node")
    builder.add_edge("planner_node", "preview_interrupt")
    builder.add_conditional_edges("preview_interrupt", after_preview)
    builder.add_edge("execution_node", "deliverable_interrupt")
    builder.add_conditional_edges("deliverable_interrupt", after_deliverable_review)
    builder.add_edge("finalization_node", "mechanic_b_node")
    builder.add_edge("mechanic_b_node", END)

    return builder


# Compile with interrupt_before on the two approval-gate nodes.
# LangGraph Cloud will pause execution before these nodes, enabling the
# interface layer to collect human input and resume the graph.
graph = build_graph().compile(
    interrupt_before=["preview_interrupt", "deliverable_interrupt"],
)
