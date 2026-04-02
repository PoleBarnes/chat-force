"""Pipeline orchestrator -- CLI entry point for the self-improving loop.

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

# WS3 -- changeset extraction
from pipeline.changeset_extractor import ChangesetExtractor

# WS5 -- PR creation and Slack notifications
from pipeline.pr_creator import PRCreator
from pipeline.slack_handler import SlackHandler

log = logging.getLogger(__name__)


def _generate_run_id() -> str:
    """Return a run ID like ``20260401-143022-a1b2c3d4``."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = secrets.token_hex(4)
    return f"{ts}-{suffix}"


def run_pipeline(task: str, config: PipelineConfig) -> dict:
    """Execute the full self-improving loop. Returns a run summary dict."""
    run_id = _generate_run_id()
    run_dir = os.path.join(config.output_base, run_id)
    os.makedirs(run_dir, exist_ok=True)

    summary = {
        "run_id": run_id,
        "task": task,
        "status": "started",
        "worker_container": None,
        "mechanic_container": None,
        "verdict": None,
        "pr_url": None,
        "error": None,
    }

    worker = WorkerManager(config, run_id)
    mechanic = MechanicManager(config, run_id)

    try:
        # -- Step 1: Run worker -----------------------------------------------
        log.info("[%s] Starting worker with task: %s", run_id, task)
        container_id = worker.start(task)
        summary["worker_container"] = container_id

        # -- Step 2: Wait for worker to finish --------------------------------
        log.info("[%s] Waiting for worker completion ...", run_id)
        worker.wait_for_completion()

        # -- Step 3: Extract changeset ----------------------------------------
        log.info("[%s] Extracting changeset ...", run_id)
        extractor = ChangesetExtractor(config, run_id)
        changeset = extractor.extract(container_id, task=task)

        # -- Step 4: Run mechanic ---------------------------------------------
        log.info("[%s] Starting mechanic evaluation ...", run_id)
        verdict = mechanic.evaluate(changeset)
        summary["verdict"] = verdict

        # -- Step 5-7: Act on verdict -----------------------------------------
        if verdict.get("approved"):
            log.info("[%s] Verdict: APPROVED -- creating PR", run_id)
            pr = PRCreator(config, run_id)
            pr_url = pr.create(changeset, verdict)
            summary["pr_url"] = pr_url
            summary["status"] = "approved"

            slack = SlackHandler(config)
            slack.notify_approved(run_id, task, pr_url)

            # Clean up both containers on success
            worker.cleanup()
            mechanic.cleanup()
        else:
            reason = verdict.get("reason", "No reason provided")
            log.info("[%s] Verdict: REJECTED -- %s", run_id, reason)
            summary["status"] = "rejected"

            slack = SlackHandler(config)
            slack.notify_rejected(run_id, task, reason)

            # Clean up on rejection
            worker.cleanup()
            mechanic.cleanup()

    except TimeoutError as exc:
        log.error("[%s] Timeout: %s", run_id, exc)
        summary["status"] = "timeout"
        summary["error"] = str(exc)
        # Keep containers alive for debugging
        mechanic.cleanup()  # mechanic is disposable

    except Exception as exc:
        log.error("[%s] Pipeline error: %s", run_id, exc, exc_info=True)
        summary["status"] = "error"
        summary["error"] = str(exc)
        # Keep containers alive for debugging

    finally:
        # Always write summary
        summary_path = os.path.join(run_dir, "summary.json")
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)
        log.info("[%s] Summary written to %s", run_id, summary_path)

        # Save worker logs if available
        try:
            logs = worker.get_logs()
            if logs:
                logs_path = os.path.join(run_dir, "worker.log")
                with open(logs_path, "w") as f:
                    f.write(logs)
        except Exception:
            pass  # best-effort

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Run the Chat-Force self-improving pipeline",
    )
    parser.add_argument(
        "--task",
        required=True,
        help="Task instruction for the Worker agent",
    )
    parser.add_argument(
        "--output-base",
        default=None,
        help="Override output directory (default: /tmp/chat-force-runs)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = PipelineConfig()
    if args.output_base:
        config.output_base = args.output_base

    summary = run_pipeline(args.task, config)

    # Exit with non-zero if the pipeline didn't succeed
    if summary["status"] not in ("approved", "rejected"):
        sys.exit(1)


if __name__ == "__main__":
    main()
