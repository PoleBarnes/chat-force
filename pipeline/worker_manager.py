"""Docker container lifecycle management for the Worker (Leo/OpenClaw)."""

import logging
import os
import subprocess
import tempfile

import docker
from docker.errors import ImageNotFound, NotFound

from pipeline.config import PipelineConfig
from pipeline.webhook_server import WebhookServer

log = logging.getLogger(__name__)


class WorkerManager:
    """Starts, monitors, and cleans up the Worker container."""

    def __init__(self, config: PipelineConfig, run_id: str):
        self.config = config
        self.run_id = run_id
        self._client = docker.from_env()
        self._container = None
        self._webhook = WebhookServer(config.webhook_host, config.webhook_port)

    # -- public API -----------------------------------------------------------

    def start(self, task: str) -> str:
        """Launch the Worker container. Returns the container ID."""
        self._ensure_image()
        self._webhook.start()

        webhook_base = f"http://host.docker.internal:{self.config.webhook_port}"

        env = {
            "TASK_INSTRUCTION": task,
            "ORCHESTRATOR_WEBHOOK_URL": webhook_base,
            "ANTHROPIC_AUTH_TOKEN": os.environ.get(
                self.config.anthropic_token_env, ""
            ),
        }

        self._container = self._client.containers.run(
            image=self.config.worker_image,
            name=f"worker-{self.run_id}",
            environment=env,
            network=self.config.docker_network,
            detach=True,
        )

        container_id = self._container.id
        log.info("Worker container started: %s (%s)", self._container.name, container_id[:12])
        return container_id

    def wait_for_completion(self) -> None:
        """Block until the worker signals completion, exits, or times out."""
        timeout = self.config.worker_timeout
        signaled = self._webhook.wait_for_completion(timeout=timeout)

        if signaled:
            log.info("Worker signaled task-complete via webhook")
            return

        self._container.reload()
        status = self._container.status

        if status in ("exited", "dead"):
            exit_code = self._container.attrs["State"]["ExitCode"]
            log.info("Worker container exited with code %d", exit_code)
            if exit_code != 0:
                logs_tail = self._container.logs(tail=50).decode(errors="replace")
                log.warning("Worker non-zero exit. Last logs:\n%s", logs_tail)
            return

        raise TimeoutError(
            f"Worker did not complete within {timeout}s (container status: {status})"
        )

    def send_feedback(self, feedback: str) -> None:
        """Send Mechanic feedback to the Worker for another iteration.

        Writes the feedback to a file inside the container. The Worker
        entrypoint polls for this file and sends it to the same OpenClaw
        session, preserving full context.
        """
        if self._container is None:
            raise RuntimeError("Worker container not running")

        self._container.reload()
        if self._container.status not in ("running",):
            raise RuntimeError(
                f"Worker container is {self._container.status}, cannot send feedback"
            )

        # Write feedback to a temp file, then docker cp into the container
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(feedback)
            tmp_path = f.name

        try:
            subprocess.run(
                ["docker", "cp", tmp_path, f"{self._container.id}:/tmp/mechanic-feedback.txt"],
                check=True,
                capture_output=True,
                timeout=10,
            )
            log.info("Feedback sent to Worker (%d chars)", len(feedback))
        finally:
            os.unlink(tmp_path)

        # Reset the webhook completion event so we can wait again
        self._webhook.reset()

    def is_alive(self) -> bool:
        """Check if the Worker container is still running."""
        if self._container is None:
            return False
        try:
            self._container.reload()
            return self._container.status == "running"
        except Exception:
            return False

    def get_logs(self) -> str:
        """Return full container logs as a string."""
        if self._container is None:
            return ""
        return self._container.logs().decode(errors="replace")

    def cleanup(self) -> None:
        """Remove the worker container and stop the webhook server."""
        self._webhook.stop()
        if self._container is None:
            return
        try:
            self._container.remove(force=True)
            log.info("Worker container removed: %s", self._container.name)
        except NotFound:
            log.debug("Worker container already removed")

    # -- internals ------------------------------------------------------------

    def _ensure_image(self) -> None:
        """Build the Worker image if it doesn't exist locally."""
        try:
            self._client.images.get(self.config.worker_image)
            log.debug("Worker image found: %s", self.config.worker_image)
        except ImageNotFound:
            log.info("Worker image not found, building %s ...", self.config.worker_image)
            self._client.images.build(
                path=".",
                dockerfile="worker/Dockerfile",
                tag=self.config.worker_image,
                rm=True,
            )
            log.info("Worker image built: %s", self.config.worker_image)
