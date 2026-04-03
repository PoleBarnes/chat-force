"""Docker container lifecycle management for the Mechanic (code reviewer)."""

import json
import logging
import os
import tempfile
import time

import docker
from docker.errors import ImageNotFound, NotFound

from pipeline.config import PipelineConfig

log = logging.getLogger(__name__)

# How often to poll for the verdict file inside the container (seconds)
_POLL_INTERVAL = 5


class MechanicManager:
    """Starts the Mechanic container, feeds it a changeset, and collects its verdict."""

    def __init__(self, config: PipelineConfig, run_id: str):
        self.config = config
        self.run_id = run_id
        self._client = docker.from_env()
        self._container = None

    # -- public API -----------------------------------------------------------

    def evaluate(self, changeset: dict) -> dict:
        """Run the Mechanic on *changeset* and return the parsed verdict.

        The changeset dict is serialised to a JSON file and bind-mounted into
        the container at ``/changeset``.  The Mechanic writes its decision to
        ``/output/verdict.json``.
        """
        self._ensure_image()

        # Prepare a focused evaluation payload from the full changeset.
        # The full changeset stays on disk for auditing; the Mechanic gets
        # only what it needs to make a decision.
        evaluation = self._prepare_evaluation(changeset)

        changeset_dir = tempfile.mkdtemp(prefix="changeset-", dir=self.config.output_base)
        changeset_path = os.path.join(changeset_dir, "changeset.json")
        with open(changeset_path, "w") as f:
            json.dump(evaluation, f, indent=2)

        output_dir = tempfile.mkdtemp(prefix="mechanic-out-", dir=self.config.output_base)

        env = {
            "TASK_DESCRIPTION": changeset.get("task", ""),
            "ANTHROPIC_AUTH_TOKEN": os.environ.get(
                self.config.anthropic_token_env, ""
            ),
        }

        self._container = self._client.containers.run(
            image=self.config.mechanic_image,
            name=f"mechanic-{self.run_id}",
            environment=env,
            volumes={
                changeset_dir: {"bind": "/changeset", "mode": "ro"},
                output_dir: {"bind": "/output", "mode": "rw"},
            },
            network=self.config.docker_network,
            detach=True,
        )
        log.info(
            "Mechanic container started: %s (%s)",
            self._container.name,
            self._container.id[:12],
        )

        verdict = self._wait_for_verdict(output_dir)
        return verdict

    def cleanup(self) -> None:
        """Remove the mechanic container."""
        if self._container is None:
            return
        try:
            self._container.remove(force=True)
            log.info("Mechanic container removed: %s", self._container.name)
        except NotFound:
            log.debug("Mechanic container already removed")

    # -- internals ------------------------------------------------------------

    def _wait_for_verdict(self, output_dir: str) -> dict:
        """Poll until ``verdict.json`` appears or timeout is reached."""
        verdict_path = os.path.join(output_dir, "verdict.json")
        deadline = time.monotonic() + self.config.mechanic_timeout

        while time.monotonic() < deadline:
            # Check if the container has exited unexpectedly
            self._container.reload()
            if self._container.status in ("exited", "dead"):
                exit_code = self._container.attrs["State"]["ExitCode"]
                if exit_code != 0:
                    logs_tail = self._container.logs(tail=50).decode(errors="replace")
                    log.error("Mechanic exited with code %d:\n%s", exit_code, logs_tail)
                    raise RuntimeError(f"Mechanic exited with code {exit_code}")

            # Check for verdict file on the host-mounted output dir
            if os.path.exists(verdict_path):
                with open(verdict_path) as f:
                    verdict = json.load(f)
                log.info("Verdict received: %s", verdict.get("verdict", verdict.get("approved", "unknown")))
                return self._validate_verdict(verdict)

            time.sleep(_POLL_INTERVAL)

        raise TimeoutError(
            f"Mechanic did not produce a verdict within {self.config.mechanic_timeout}s"
        )

    def _ensure_image(self) -> None:
        """Build the Mechanic image if it doesn't exist locally."""
        try:
            self._client.images.get(self.config.mechanic_image)
            log.debug("Mechanic image found: %s", self.config.mechanic_image)
        except ImageNotFound:
            log.info("Mechanic image not found, building %s ...", self.config.mechanic_image)
            self._client.images.build(
                path=".",
                dockerfile="mechanic/Dockerfile",
                tag=self.config.mechanic_image,
                rm=True,
            )
            log.info("Mechanic image built: %s", self.config.mechanic_image)

    @staticmethod
    def _prepare_evaluation(changeset: dict) -> dict:
        """Distill the full changeset into a focused evaluation payload.

        The Mechanic needs to review the actual code changes, not wade through
        thousands of node_modules entries.  The full changeset stays on disk
        for auditing; this produces the subset the Mechanic can reason about.
        """
        git = changeset.get("git_changes", {})
        docker = changeset.get("docker_changes", {})
        telemetry = changeset.get("telemetry", {})
        output = changeset.get("output_files", {})

        # ── Docker changes: summarize instead of listing every path ──
        added = docker.get("added", [])
        changed = docker.get("changed", [])
        deleted = docker.get("deleted", [])

        # Categorise docker changes into meaningful groups
        categories: dict[str, int] = {}
        significant_paths: list[str] = []
        for path in added:
            if "/node_modules/" in path:
                categories["node_modules"] = categories.get("node_modules", 0) + 1
            elif "/.cache/" in path or "/.npm/" in path:
                categories["caches"] = categories.get("caches", 0) + 1
            elif "/workspace/config/" in path:
                significant_paths.append(path)
            else:
                categories["other"] = categories.get("other", 0) + 1

        docker_summary = {
            "total_added": len(added),
            "total_changed": len(changed),
            "total_deleted": len(deleted),
            "categories": categories,
            "significant_paths": significant_paths[:100],  # cap for safety
        }

        # ── Telemetry: keep key facts, truncate verbose logs ──
        logs = telemetry.get("container_logs", "")
        # Keep last 100 lines of logs (most relevant)
        log_lines = logs.splitlines()
        if len(log_lines) > 100:
            truncated_logs = (
                f"[...truncated {len(log_lines) - 100} lines...]\n"
                + "\n".join(log_lines[-100:])
            )
        else:
            truncated_logs = logs

        telemetry_summary = {
            "exit_code": telemetry.get("exit_code"),
            "duration_seconds": telemetry.get("duration_seconds"),
            "started_at": telemetry.get("started_at"),
            "finished_at": telemetry.get("finished_at"),
            "container_logs": truncated_logs,
        }

        # ── Output files: list what was produced ──
        output_summary = []
        for f in output.get("files", []):
            path = f.get("container_path", f.get("local_path", ""))
            output_summary.append(path)

        return {
            "run_id": changeset.get("run_id"),
            "task": changeset.get("task"),
            "timestamp": changeset.get("timestamp"),
            "git_changes": git,  # full git changes — this IS the code review
            "docker_changes_summary": docker_summary,
            "telemetry": telemetry_summary,
            "output_files": output_summary,
        }

    @staticmethod
    def _validate_verdict(verdict: dict) -> dict:
        """Ensure the verdict has the required fields.

        The Mechanic outputs ``"verdict": "approve"|"reject"`` per its AGENTS.md.
        We normalise to an ``"approved"`` bool for the pipeline.
        """
        # Handle both formats: "verdict": "approve" or "approved": True
        if "verdict" in verdict and "approved" not in verdict:
            verdict["approved"] = verdict["verdict"] == "approve"
        elif "approved" not in verdict:
            raise ValueError("Verdict missing 'verdict' or 'approved' field")
        else:
            verdict["approved"] = bool(verdict["approved"])

        if not verdict["approved"]:
            # Prefer rejection_reason (AGENTS.md schema), fall back to reason
            if "rejection_reason" in verdict and "reason" not in verdict:
                verdict["reason"] = verdict["rejection_reason"]
            verdict.setdefault("reason", "No reason provided")

        return verdict
