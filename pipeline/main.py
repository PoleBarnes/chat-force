"""Pipeline orchestrator — CLI entry point for the self-improving loop.

Usage:
    uv run --python 3.13 --with docker,slack_sdk python -m pipeline.main --task "Refactor the auth module"
"""

import argparse
import json
import logging
import os
import secrets
import sys
from datetime import datetime, timezone

from pipeline.config import PipelineConfig
from pipeline.worker_manager import WorkerManager
from pipeline.mechanic_manager import MechanicManager
from pipeline.changeset_extractor import ChangesetExtractor
from pipeline.pr_creator import PRCreator
from pipeline.slack_handler import SlackHandler

log = logging.getLogger(__name__)

MAX_ITERATIONS = 3


def _generate_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{ts}-{secrets.token_hex(4)}"


def run_pipeline(task: str, config: PipelineConfig, reply_channel: str | None = None) -> dict:
    """Execute the self-improving loop with feedback iterations.

    The Worker runs the task, the Mechanic evaluates, and if rejected the
    Mechanic's feedback is sent back to the Worker (same session, same
    container). This repeats up to MAX_ITERATIONS times.

    Outcomes:
        - "approved"  → PR created
        - "rejected"  → linear_issue proposed or changes discarded
        - "timeout"   → Worker or Mechanic timed out
        - "error"     → unexpected failure
    """
    run_id = _generate_run_id()
    run_dir = os.path.join(config.output_base, run_id)
    os.makedirs(run_dir, exist_ok=True)

    summary = {
        "run_id": run_id,
        "task": task,
        "status": "started",
        "iterations": 0,
        "worker_container": None,
        "verdict": None,
        "pr_url": None,
        "error": None,
    }

    worker = WorkerManager(config, run_id)
    mechanic = MechanicManager(config, run_id)
    slack = SlackHandler(config, reply_channel)

    try:
        # ── Start Worker ──
        log.info("[%s] Starting worker with task: %s", run_id, task)
        container_id = worker.start(task)
        summary["worker_container"] = container_id

        log.info("[%s] Waiting for worker completion ...", run_id)
        worker.wait_for_completion()

        # ── Feedback loop ──
        previous_rejections = []

        for iteration in range(1, MAX_ITERATIONS + 1):
            summary["iterations"] = iteration
            log.info("[%s] Iteration %d/%d: extracting changeset ...", run_id, iteration, MAX_ITERATIONS)

            # Extract changeset
            extractor = ChangesetExtractor(config, run_id)
            changeset = extractor.extract(container_id, task=task)
            changeset["previous_rejections"] = previous_rejections

            # Mechanic evaluates
            log.info("[%s] Iteration %d/%d: mechanic evaluating ...", run_id, iteration, MAX_ITERATIONS)
            verdict = mechanic.evaluate(changeset)
            summary["verdict"] = verdict

            # Default: approved → "pr", rejected → continue loop (no disposition = iterate)
            disposition = verdict.get("disposition", "pr" if verdict.get("approved") else None)

            if verdict.get("approved"):
                # ── APPROVED → create PR ──
                log.info("[%s] APPROVED on iteration %d (confidence: %s)", run_id, iteration, verdict.get("confidence"))
                pr = PRCreator(config, run_id)
                pr_url = pr.create(changeset, verdict)
                summary["pr_url"] = pr_url
                summary["status"] = "approved"
                slack.notify_approved(run_id, task, pr_url)
                break

            # ── REJECTED ──
            reason = verdict.get("reason", verdict.get("rejection_reason", "No reason"))
            feedback = verdict.get("feedback", [])
            confidence = verdict.get("confidence", 0)
            log.info("[%s] REJECTED on iteration %d (confidence: %s): %s", run_id, iteration, confidence, reason[:200])

            previous_rejections.append({
                "iteration": iteration,
                "reason": reason,
                "confidence": confidence,
                "feedback": feedback,
            })

            # Check disposition — Mechanic may say to bail
            if disposition == "discard":
                log.info("[%s] Mechanic says discard — bailing", run_id)
                summary["status"] = "rejected"
                slack.notify_rejected(run_id, task, reason)
                break

            if disposition == "linear_issue":
                log.info("[%s] Mechanic suggests Linear issue", run_id)
                summary["status"] = "linear_proposed"
                summary["linear_proposal"] = {
                    "reason": verdict.get("disposition_reason", reason),
                    "summary": verdict.get("summary", ""),
                }
                slack.notify_linear_proposal(run_id, task, verdict)
                break

            # Check if we have iterations left
            if iteration == MAX_ITERATIONS:
                log.info("[%s] Max iterations reached — bailing", run_id)
                summary["status"] = "rejected"
                slack.notify_rejected(run_id, task, f"Failed after {MAX_ITERATIONS} iterations. Last: {reason}")
                break

            # Check if Worker is still alive
            if not worker.is_alive():
                log.error("[%s] Worker died during feedback loop", run_id)
                summary["status"] = "error"
                summary["error"] = "Worker container died during feedback loop"
                slack.notify_rejected(run_id, task, "Worker crashed during iteration")
                break

            # ── Send feedback to Worker for next iteration ──
            feedback_text = _format_feedback(feedback, reason, iteration)
            log.info("[%s] Sending feedback to Worker (%d items)", run_id, len(feedback))
            worker.send_feedback(feedback_text)

            log.info("[%s] Waiting for Worker iteration %d ...", run_id, iteration + 1)
            worker.wait_for_completion()

            # Clean up the mechanic container from this iteration
            mechanic.cleanup()

    except TimeoutError as exc:
        log.error("[%s] Timeout: %s", run_id, exc)
        summary["status"] = "timeout"
        summary["error"] = str(exc)

    except Exception as exc:
        log.error("[%s] Pipeline error: %s", run_id, exc, exc_info=True)
        summary["status"] = "error"
        summary["error"] = str(exc)

    finally:
        # Always write summary
        summary_path = os.path.join(run_dir, "summary.json")
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2, default=str)
        log.info("[%s] Summary written to %s", run_id, summary_path)

        # Save worker logs
        try:
            logs = worker.get_logs()
            if logs:
                with open(os.path.join(run_dir, "worker.log"), "w") as f:
                    f.write(logs)
        except Exception:
            pass

        # Clean up containers
        worker.cleanup()
        mechanic.cleanup()

    return summary


def _format_feedback(feedback: list[str], reason: str, iteration: int) -> str:
    """Format Mechanic feedback into a message for the Worker."""
    parts = [
        f"The Mechanic reviewed your changes (iteration {iteration}) and found issues to fix.\n",
        f"Rejection reason: {reason}\n",
    ]
    if feedback:
        parts.append("Specific items to address:")
        for i, item in enumerate(feedback, 1):
            parts.append(f"  {i}. {item}")
        parts.append("")
    parts.append("Please fix these issues now. You have the same session context — "
                 "you know what you built and what tools you used. Make the changes and they'll be re-evaluated.")
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(
        description="Run the Chat-Force self-improving pipeline",
    )
    parser.add_argument("--task", required=True, help="Task instruction for the Worker agent")
    parser.add_argument("--output-base", default=None, help="Override output directory")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = PipelineConfig()
    if args.output_base:
        config.output_base = args.output_base

    summary = run_pipeline(args.task, config)

    if summary["status"] not in ("approved", "rejected", "linear_proposed"):
        sys.exit(1)


if __name__ == "__main__":
    main()
