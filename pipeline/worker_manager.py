"""Docker container lifecycle management for the Worker (Leo/OpenClaw)."""

import logging
import os

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

        # The webhook URL the worker should POST to from inside the container.
        # host.docker.internal works on Docker Desktop; on Linux the host
        # gateway is typically 172.17.0.1 but the Docker network alias works
        # with modern Docker.
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
            # Do NOT use auto_remove -- we need the container for changeset extraction
        )

        container_id = self._container.id
        log.info("Worker container started: %s (%s)", self._container.name, container_id[:12])
        return container_id

    def wait_for_completion(self) -> None:
        """Block until the worker signals completion, exits, or times out.

        Priority order:
        1. Webhook task-complete signal
        2. Container exits on its own
        3. Timeout
        """
        timeout = self.config.worker_timeout

        # Wait for either webhook signal or container exit
        signaled = self._webhook.wait_for_completion(timeout=timeout)

        if signaled:
            log.info("Worker signaled task-complete via webhook")
            self._webhook.stop()
            return

        # No webhook signal within timeout -- check if the container exited
        self._container.reload()
        status = self._container.status

        self._webhook.stop()

        if status in ("exited", "dead"):
            exit_code = self._container.attrs["State"]["ExitCode"]
            log.info("Worker container exited with code %d", exit_code)
            if exit_code != 0:
                logs_tail = self._container.logs(tail=50).decode(errors="replace")
                log.warning("Worker non-zero exit. Last logs:\n%s", logs_tail)
            return

        # Neither signal nor exit -- genuine timeout
        raise TimeoutError(
            f"Worker did not complete within {timeout}s (container status: {status})"
        )

    def get_logs(self) -> str:
        """Return full container logs as a string."""
        if self._container is None:
            return ""
        return self._container.logs().decode(errors="replace")

    def cleanup(self) -> None:
        """Remove the worker container."""
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
