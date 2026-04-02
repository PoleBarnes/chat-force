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

import logging
from enum import Enum
from typing import Any, Dict, List, Optional

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from ..nodes.agents import dispatch as agent_dispatch
from ..nodes.context import assemble_context
from ..nodes.llm import call_claude, call_claude_structured, get_temperature
from ..nodes.routing import should_dispatch
from ..nodes.sop_loader import load_sop, match_sop
from ..nodes.specialists import get_specialist_prompt, SPECIALIST_PROMPTS

logger = logging.getLogger(__name__)


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
    matched_sop: Optional[str] = None
    context: dict[str, Any] = Field(default_factory=dict)

    # -- Planning --
    plan: list[TaskStep] = Field(default_factory=list)
    plan_approved: bool = False

    # -- Execution --
    execution_results: dict[str, Any] = Field(default_factory=dict)
    deliverables: list[dict[str, Any]] = Field(default_factory=list)
    current_step_index: int = 0  # Track position in plan for resume after approval gate
    approval_gate_id: str = ""   # Which approval gate we're paused at (empty = none)

    # -- Review --
    deliverables_approved: bool = False

    # -- Feedback (H11: carry human feedback on rejection loops) --
    plan_feedback: str = ""           # Human's feedback when rejecting a plan
    deliverable_feedback: str = ""    # Human's feedback when rejecting deliverables

    # -- Output --
    final_output: dict[str, Any] = Field(default_factory=dict)

    # -- Mechanic B --
    mechanic_b_report: dict[str, Any] = Field(default_factory=dict)

    # -- Meta --
    status: TaskStatus = TaskStatus.PENDING
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------

def entry_node(state: GraphState) -> dict[str, Any]:
    """Parse the user's input, load workspace/thread context, and match an SOP."""
    workspace_id = state.workspace_id or "default"
    errors: list[str] = []

    # Match against registered SOPs first (needed for skill selection in context)
    matched_sop: Optional[str] = None
    try:
        matched_sop = match_sop(state.raw_input, workspace_id)
    except Exception as exc:
        logger.error("SOP matching failed: %s", exc)
        errors.append(f"SOP matching error: {exc}")

    # Assemble context from all tiers, including relevant skills (H7)
    try:
        assembled = assemble_context(
            workspace_id=workspace_id,
            thread_messages=state.context.get("thread_messages", []),
            current_input=state.raw_input,
            token_budget=100_000,
            matched_sop=matched_sop,
        )
    except Exception as exc:
        logger.error("Context assembly failed: %s", exc)
        assembled = state.raw_input
        errors.append(f"Context assembly error: {exc}")

    return {
        "status": TaskStatus.PLANNING,
        "context": {
            "assembled": assembled,
            "thread_messages": state.context.get("thread_messages", []),
        },
        "matched_sop": matched_sop,
        "errors": state.errors + errors,
    }


def planner_node(state: GraphState) -> dict[str, Any]:
    """Create a task breakdown (plan) for the incoming request.

    If an SOP was matched, loads its steps directly. Otherwise, uses Claude
    to decompose the task into ordered steps with specialist assignments.
    """
    workspace_id = state.workspace_id or "default"
    errors: list[str] = []

    # Path A: SOP-driven plan
    if state.matched_sop:
        try:
            sop = load_sop(workspace_id, state.matched_sop)
            plan = []
            for i, step_def in enumerate(sop.steps):
                if step_def.type == "approval_gate":
                    # Approval gates become steps with a special specialist marker
                    plan.append(TaskStep(
                        id=step_def.id or f"step-{i+1}",
                        description=step_def.description,
                        specialist="human_approval",
                        depends_on=step_def.depends_on,
                    ))
                else:
                    specialist = step_def.specialist or "general"
                    # Normalize "openclaw" agent to "general" specialist
                    if specialist == "openclaw":
                        specialist = "general"
                    plan.append(TaskStep(
                        id=step_def.id or f"step-{i+1}",
                        description=step_def.description,
                        specialist=specialist,
                        depends_on=step_def.depends_on,
                    ))

            return {
                "status": TaskStatus.AWAITING_PLAN_APPROVAL,
                "plan": plan,
                "errors": state.errors + errors,
            }
        except FileNotFoundError:
            logger.warning("Matched SOP '%s' not found, falling back to LLM planning", state.matched_sop)
            errors.append(f"SOP '{state.matched_sop}' not found; using LLM planning.")
        except Exception as exc:
            logger.error("SOP loading failed: %s", exc)
            errors.append(f"SOP loading error: {exc}")

    # Path B: LLM-driven planning
    context_text = state.context.get("assembled", state.raw_input)

    planning_prompt = f"""Analyze this task and break it down into concrete, actionable steps.

Task: {state.raw_input}

Context:
{context_text}

For each step, provide:
- id: A short kebab-case identifier (e.g. "research-topic", "draft-copy")
- description: What this step accomplishes
- specialist: One of: researcher, writer, editor, analyst, strategist, developer, general
- depends_on: List of step IDs that must complete before this one (empty list if none)

Order the steps logically. Identify which steps can run in parallel (no dependencies on each other).
Aim for 3-7 steps for most tasks. Be specific and actionable, not vague.

Return your answer as a JSON object with a single key "steps" containing an array of step objects."""

    # H11: Include revision feedback when re-planning after rejection
    if state.plan_feedback:
        planning_prompt += (
            f"\n\n## Revision Request\n"
            f"The previous plan was rejected. Feedback: {state.plan_feedback}"
        )

    plan_schema = {
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "description": {"type": "string"},
                        "specialist": {"type": "string"},
                        "depends_on": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["id", "description", "specialist"],
                },
            },
        },
        "required": ["steps"],
    }

    try:
        result = call_claude_structured(
            prompt=planning_prompt,
            system=(
                "You are a task planning specialist. Break down tasks into clear, "
                "ordered steps that can be executed by specialist agents. "
                "Be thorough but efficient — avoid unnecessary steps."
            ),
            response_schema=plan_schema,
            model="claude-sonnet-4-6",
            temperature=0.0,
        )
        plan = [
            TaskStep(
                id=s["id"],
                description=s["description"],
                specialist=s.get("specialist", "general"),
                depends_on=s.get("depends_on", []),
            )
            for s in result.get("steps", [])
        ]
    except Exception as exc:
        logger.error("LLM planning failed: %s", exc)
        errors.append(f"Planning error: {exc}")
        plan = [
            TaskStep(
                id="fallback-step",
                description=f"Complete the task: {state.raw_input}",
                specialist="general",
            ),
        ]

    return {
        "status": TaskStatus.AWAITING_PLAN_APPROVAL,
        "plan": plan,
        "errors": state.errors + errors,
    }


def preview_interrupt(state: GraphState) -> dict[str, Any]:
    """Show the plan to the human and wait for approval.

    This node is configured with ``interrupt_before`` so the graph pauses
    *before* entering it. The interface layer reads the current state (which
    contains the plan), renders it for the user, and resumes the graph with
    ``plan_approved`` set to ``True`` (or ``False`` for rejection).

    When the graph resumes into this node, we read the decision.
    """
    # Format the plan into a structured preview dict that the interface
    # layer can render (Slack Block Kit, Google Chat card, etc.)
    plan_preview = {
        "title": "Task Plan",
        "steps": [
            {
                "id": step.id,
                "description": step.description,
                "specialist": step.specialist,
                "depends_on": step.depends_on,
            }
            for step in state.plan
        ],
        "total_steps": len(state.plan),
        "has_approval_gates": any(
            s.specialist == "human_approval" for s in state.plan
        ),
    }

    # The plan_approved field is set by the interface layer when it resumes
    # the graph. We pass through whatever value is in state.
    return {
        "context": {
            **state.context,
            "plan_preview": plan_preview,
        },
        "plan_approved": state.plan_approved,
        "status": (
            TaskStatus.EXECUTING
            if state.plan_approved
            else TaskStatus.PLANNING
        ),
    }


def execution_node(state: GraphState) -> dict[str, Any]:
    """Execute the approved plan by dispatching each step to a specialist.

    Steps are executed in dependency order starting from ``current_step_index``
    (which is 0 on the first run and advanced past approval gates on resume).
    When a ``human_approval`` step is encountered, execution pauses: partial
    results are returned along with the ``approval_gate_id`` so the graph can
    route to the deliverable interrupt for human review.

    After the human approves, the graph re-enters this node with
    ``current_step_index`` pointing past the gate so execution continues.
    """
    # Carry forward previously accumulated results when resuming after a gate
    results: dict[str, Any] = dict(state.execution_results)
    deliverables: list[dict[str, Any]] = list(state.deliverables)
    errors: list[str] = list(state.errors)
    context_text = state.context.get("assembled", state.raw_input)

    # Build lookup of completed step outputs for dependency injection.
    # This includes results from prior runs (before an approval gate).
    completed: dict[str, str] = {}
    for step_id, result in results.items():
        if isinstance(result, dict) and result.get("status") == "completed":
            completed[step_id] = result.get("output", "")

    # Resume from where we left off (0 on first run, past the gate on resume)
    start_index = state.current_step_index

    for idx in range(start_index, len(state.plan)):
        step = state.plan[idx]

        # ------------------------------------------------------------------
        # Approval gate: pause execution and hand control to the interrupt
        # ------------------------------------------------------------------
        if step.specialist == "human_approval":
            results[step.id] = {
                "status": "pending_approval",
                "output": f"Approval gate '{step.id}' reached — awaiting human review.",
            }
            return {
                "execution_results": results,
                "deliverables": deliverables,
                # Advance past the gate so the next run starts on the step after it
                "current_step_index": idx + 1,
                "approval_gate_id": step.id,
                "status": TaskStatus.AWAITING_DELIVERABLE_REVIEW,
                "errors": errors,
            }

        # ------------------------------------------------------------------
        # Normal task step: dispatch to specialist
        # ------------------------------------------------------------------

        # Gather results from dependencies
        dependency_context = ""
        for dep_id in step.depends_on:
            dep_output = completed.get(dep_id, "")
            if dep_output:
                dependency_context += f"\n\n### Results from '{dep_id}':\n{dep_output}"

        # Build the specialist prompt
        specialist_system = get_specialist_prompt(step.specialist)
        step_prompt = f"""Execute the following task step:

## Step: {step.id}
{step.description}

## Overall Task
{state.raw_input}

## Context
{context_text}
{dependency_context if dependency_context else ""}

Produce a thorough, complete deliverable for this step. Be specific and actionable."""

        # H11: Include deliverable feedback when re-executing after rejection
        if state.deliverable_feedback:
            step_prompt += (
                f"\n\n## Revision Request\n"
                f"The previous deliverables were rejected. Feedback: {state.deliverable_feedback}"
            )

        try:
            # Use Sonnet for routine steps, Opus for complex specialist work
            model = "claude-sonnet-4-6"
            if step.specialist in ("strategist", "analyst", "developer"):
                model = "claude-opus-4-6"

            # H8: Use creative temperature for creative specialists
            creative_specialists = {"writer", "general"}
            temperature = (
                get_temperature("creative")
                if step.specialist in creative_specialists
                else 0.0
            )

            output = call_claude(
                prompt=step_prompt,
                system=specialist_system,
                model=model,
                temperature=temperature,
                max_tokens=4096,
            )
            results[step.id] = {"status": "completed", "output": output}
            completed[step.id] = output
            deliverables.append({
                "step_id": step.id,
                "specialist": step.specialist,
                "content": output,
            })
        except Exception as exc:
            error_msg = f"Step '{step.id}' failed: {exc}"
            logger.error(error_msg)
            errors.append(error_msg)
            results[step.id] = {"status": "error", "error": str(exc)}
            completed[step.id] = f"[ERROR: {exc}]"

    # All steps complete (no more approval gates) — proceed to final review
    return {
        "execution_results": results,
        "deliverables": deliverables,
        "current_step_index": len(state.plan),
        "approval_gate_id": "",  # Clear — no gate active
        "status": TaskStatus.AWAITING_DELIVERABLE_REVIEW,
        "errors": errors,
    }


def deliverable_interrupt(state: GraphState) -> dict[str, Any]:
    """Show deliverables to the human for review.

    Like ``preview_interrupt``, this node is configured with
    ``interrupt_before``. The interface layer renders the deliverables and
    collects feedback, then resumes the graph with ``deliverables_approved``.

    This node serves double duty:
    - **Approval gates:** When ``approval_gate_id`` is set, this is a
      mid-execution gate (e.g. research_review). After approval the graph
      routes back to ``execution_node`` to continue from the next step.
    - **Final review:** When ``approval_gate_id`` is empty, all steps are
      done and this is the final deliverable review before finalization.
    """
    at_gate = bool(state.approval_gate_id)

    # Build a review-friendly summary
    deliverable_summary = {
        "title": (
            f"Approval Gate: {state.approval_gate_id}"
            if at_gate
            else "Deliverables for Review"
        ),
        "approval_gate_id": state.approval_gate_id,
        "is_approval_gate": at_gate,
        "items": [
            {
                "step_id": d["step_id"],
                "specialist": d.get("specialist", ""),
                "content_preview": d["content"][:500] + ("..." if len(d["content"]) > 500 else ""),
                "content_length": len(d["content"]),
            }
            for d in state.deliverables
        ],
        "total_items": len(state.deliverables),
        "errors": [
            step_id
            for step_id, result in state.execution_results.items()
            if result.get("status") == "error"
        ],
    }

    return {
        "context": {
            **state.context,
            "deliverable_summary": deliverable_summary,
        },
        "deliverables_approved": state.deliverables_approved,
        "status": (
            TaskStatus.FINALIZING
            if state.deliverables_approved and not at_gate
            else TaskStatus.EXECUTING
        ),
    }


def finalization_node(state: GraphState) -> dict[str, Any]:
    """Package outputs into the final deliverable set with a summary."""
    errors: list[str] = list(state.errors)

    # Use Claude to generate a concise summary of all deliverables
    deliverable_texts = []
    for d in state.deliverables:
        deliverable_texts.append(
            f"### {d['step_id']} ({d.get('specialist', 'general')})\n{d['content']}"
        )
    all_deliverables = "\n\n---\n\n".join(deliverable_texts)

    try:
        summary = call_claude(
            prompt=f"""Summarize the following task deliverables into a concise executive summary.
Include: what was accomplished, key findings or outputs, and any next steps.

Original task: {state.raw_input}

Deliverables:
{all_deliverables}""",
            system="You are a concise summarizer. Produce a clear 2-4 paragraph summary.",
            model="claude-sonnet-4-6",
            temperature=0.0,
            max_tokens=1024,
        )
    except Exception as exc:
        logger.error("Summary generation failed: %s", exc)
        summary = f"Task completed with {len(state.deliverables)} deliverables."
        errors.append(f"Summary generation error: {exc}")

    return {
        "final_output": {
            "summary": summary,
            "deliverables": state.deliverables,
            "task": state.raw_input,
            "workspace_id": state.workspace_id,
            "matched_sop": state.matched_sop,
            "step_count": len(state.plan),
            "error_count": len([
                r for r in state.execution_results.values()
                if isinstance(r, dict) and r.get("status") == "error"
            ]),
        },
        "status": TaskStatus.ANALYZING,
        "errors": errors,
    }


def mechanic_b_node(state: GraphState) -> dict[str, Any]:
    """Analyze the execution using the Mechanic B sub-graph.

    Collects execution metadata and invokes the Mechanic B analysis pipeline
    to produce quality scores and improvement proposals.
    """
    from .mechanic_b import graph as mechanic_b_graph

    errors: list[str] = list(state.errors)

    try:
        # Build input state for Mechanic B
        mechanic_input = {
            "run_id": state.thread_id,
            "trace_id": state.thread_id,
            "thread_id": state.thread_id,
            "workspace_id": state.workspace_id,
            # Pass execution data so Mechanic B can analyze it
            "trace_data": {
                "task": state.raw_input,
                "matched_sop": state.matched_sop,
                "plan": [s.model_dump() for s in state.plan],
                "execution_results": state.execution_results,
                "deliverables": state.deliverables,
                "errors": state.errors,
            },
        }

        result = mechanic_b_graph.invoke(mechanic_input)
        report = result.get("report", {})
    except Exception as exc:
        logger.error("Mechanic B analysis failed: %s", exc)
        errors.append(f"Mechanic B error: {exc}")
        report = {
            "error": str(exc),
            "summary": "Mechanic B analysis could not be completed.",
            "quality_scores": {},
            "proposals": [],
        }

    return {
        "mechanic_b_report": report,
        "status": TaskStatus.COMPLETE,
        "errors": errors,
    }


def mechanic_approval_interrupt(state: GraphState) -> dict[str, Any]:
    """Present Mechanic B proposals for human approval.

    This node is configured with ``interrupt_before`` so the graph pauses
    before entering it. The interface layer renders the proposals and
    collects Travis's decision (approve, reject, or defer each proposal).

    Proposals may include SOP improvements, new skill suggestions, or
    configuration changes that require human sign-off before applying.
    """
    report = state.mechanic_b_report
    proposals = report.get("proposals", [])

    return {
        "context": {
            **state.context,
            "mechanic_proposals": proposals,
            "mechanic_summary": report.get("summary", ""),
        },
    }


# ---------------------------------------------------------------------------
# Routing helpers
# ---------------------------------------------------------------------------

def after_preview(state: GraphState) -> str:
    """Route after the plan preview interrupt.

    If the human rejected the plan, route back to planner_node so Claude
    can revise based on the feedback stored in context.
    """
    if state.plan_approved:
        return "execution_node"
    return "planner_node"


def after_deliverable_review(state: GraphState) -> str:
    """Route after the deliverable review interrupt.

    Three cases:
    1. **At an approval gate, approved:** Route back to ``execution_node``
       to continue executing the remaining steps after the gate.
    2. **At an approval gate, rejected:** Route to END — the workflow is
       cancelled at this gate.
    3. **Final review (no gate), approved:** Route to ``finalization_node``.
    4. **Final review, rejected:** Route back to ``execution_node`` for
       selective re-execution.
    """
    at_gate = bool(state.approval_gate_id)

    if at_gate:
        if state.deliverables_approved:
            # Approved at gate — continue execution from where we left off
            return "execution_node"
        else:
            # Rejected at gate — abort the workflow
            return END

    # Final deliverable review (not at a gate)
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
    builder.add_node("mechanic_approval_interrupt", mechanic_approval_interrupt)

    # -- Set entry point --
    builder.set_entry_point("entry_node")

    # -- Add edges --
    builder.add_edge("entry_node", "planner_node")
    builder.add_edge("planner_node", "preview_interrupt")
    builder.add_conditional_edges("preview_interrupt", after_preview)
    builder.add_edge("execution_node", "deliverable_interrupt")
    builder.add_conditional_edges("deliverable_interrupt", after_deliverable_review)
    builder.add_edge("finalization_node", "mechanic_b_node")
    # H10: Route Mechanic B proposals through approval interrupt before ending
    builder.add_edge("mechanic_b_node", "mechanic_approval_interrupt")
    builder.add_edge("mechanic_approval_interrupt", END)

    return builder


# Compile with interrupt_before on approval-gate nodes.
# LangGraph Cloud will pause execution before these nodes, enabling the
# interface layer to collect human input and resume the graph.
graph = build_graph().compile(
    interrupt_before=[
        "preview_interrupt",
        "deliverable_interrupt",
        "mechanic_approval_interrupt",
    ],
)
