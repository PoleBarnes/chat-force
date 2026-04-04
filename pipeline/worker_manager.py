"""Docker container lifecycle management for the Worker (Leo/Agent SDK)."""

import json
import logging
import os
import subprocess
import tempfile
import time

import docker
from docker.errors import APIError, ImageNotFound, NotFound

from pipeline.config import PipelineConfig

log = logging.getLogger(__name__)


class WorkerManager:
    """Starts, monitors, and cleans up the Worker container."""

    def __init__(self, config: PipelineConfig, run_id: str):
        self.config = config
        self.run_id = run_id
        self._client = docker.from_env()
        self._container = None

    # -- public API -----------------------------------------------------------

    def _ensure_network(self) -> None:
        """Create the Docker network if it does not already exist."""
        try:
            self._client.networks.create(
                self.config.docker_network,
                driver="bridge",
                check_duplicate=True,
            )
            log.debug("Docker network created: %s", self.config.docker_network)
        except APIError:
            log.debug("Docker network already exists: %s", self.config.docker_network)

    def start(self, task: str) -> str:
        """Launch the Worker container. Returns the container ID."""
        self._ensure_network()
        self._ensure_image()

        env = {
            "TASK_INSTRUCTION": task,
            self.config.claude_code_token_env: os.environ.get(
                self.config.claude_code_token_env, ""
            ),
            "ALLOWED_TOOLS": ",".join(self.config.allowed_tools),
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
        """Block until the worker creates the completion sentinel or times out."""
        if self._container is None:
            raise RuntimeError("Worker container not running")

        deadline = time.monotonic() + self.config.worker_timeout
        last_status = "unknown"

        while time.monotonic() < deadline:
            result = subprocess.run(
                ["docker", "exec", self._container.id, "test", "-f", "/tmp/session-complete"],
                check=False,
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0:
                log.info("Worker completion sentinel detected")
                error = self.get_error()
                if error:
                    log.warning("Worker reported error: %s", error[:500])
                return

            self._container.reload()
            last_status = self._container.status
            if last_status in ("exited", "dead"):
                exit_code = self._container.attrs["State"]["ExitCode"]
                log.warning(
                    "Worker container exited before completion sentinel appeared (code %d)",
                    exit_code,
                )
                break

            time.sleep(2)

        raise TimeoutError(
            f"Worker did not complete within {self.config.worker_timeout}s "
            f"(container status: {last_status})"
        )

    def send_message(self, message: str) -> None:
        """Send a follow-up message to the Worker for another turn.

        Writes the message to a file inside the container. The Worker
        entrypoint polls for this file and sends it to the same Agent SDK
        session, preserving full context.
        """
        if self._container is None:
            raise RuntimeError("Worker container not running")

        self._container.reload()
        if self._container.status not in ("running",):
            raise RuntimeError(
                f"Worker container is {self._container.status}, cannot send message"
            )

        # Write message to a temp file, then docker cp into the container
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(message)
            tmp_path = f.name

        try:
            subprocess.run(
                ["docker", "exec", self._container.id, "rm", "-f", "/tmp/session-complete"],
                check=False,
                capture_output=True,
                timeout=5,
            )
            subprocess.run(
                ["docker", "cp", tmp_path, f"{self._container.id}:/tmp/next-message.txt"],
                check=True,
                capture_output=True,
                timeout=10,
            )
            subprocess.run(
                ["docker", "exec", self._container.id, "chmod", "644", "/tmp/next-message.txt"],
                check=False,  # best effort
                capture_output=True,
                timeout=5,
            )
            log.info("Message sent to Worker (%d chars)", len(message))
        finally:
            os.unlink(tmp_path)

    def send_feedback(self, feedback: str) -> None:
        """Backward-compatible alias for send_message()."""
        return self.send_message(feedback)

    def get_response(self) -> str:
        """Retrieve the Worker's latest response text.

        Copies /tmp/latest-response.txt from the container and returns it as plain text.
        """
        if self._container is None:
            raise RuntimeError("Worker container not running")

        with tempfile.NamedTemporaryFile(mode="r", suffix=".txt", delete=False) as f:
            tmp_path = f.name

        try:
            subprocess.run(
                ["docker", "cp", f"{self._container.id}:/tmp/latest-response.txt", tmp_path],
                check=True,
                capture_output=True,
                timeout=10,
            )
            with open(tmp_path, "r") as f:
                return f.read()
        except (OSError, subprocess.CalledProcessError):
            log.warning("Could not copy latest-response.txt from Worker")
            return ""
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def get_tool_log(self) -> list[dict]:
        """Retrieve structured tool-call logs from the Worker."""
        if self._container is None:
            raise RuntimeError("Worker container not running")

        with tempfile.NamedTemporaryFile(mode="r", suffix=".jsonl", delete=False) as f:
            tmp_path = f.name

        try:
            subprocess.run(
                ["docker", "cp", f"{self._container.id}:/tmp/tool-log.jsonl", tmp_path],
                check=True,
                capture_output=True,
                timeout=10,
            )
            with open(tmp_path, "r") as f:
                return [json.loads(line) for line in f if line.strip()]
        except (OSError, json.JSONDecodeError, subprocess.CalledProcessError):
            log.warning("Could not copy tool-log.jsonl from Worker")
            return []
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def get_usage(self) -> dict:
        """Retrieve usage metadata from the Worker."""
        if self._container is None:
            raise RuntimeError("Worker container not running")

        with tempfile.NamedTemporaryFile(mode="r", suffix=".json", delete=False) as f:
            tmp_path = f.name

        try:
            subprocess.run(
                ["docker", "cp", f"{self._container.id}:/tmp/usage.json", tmp_path],
                check=True,
                capture_output=True,
                timeout=10,
            )
            with open(tmp_path, "r") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError, subprocess.CalledProcessError):
            log.warning("Could not copy usage.json from Worker")
            return {}
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def get_error(self) -> str | None:
        """Check for a crash error file in the Worker container.

        Returns the error text if /tmp/worker-error.txt exists, None otherwise.
        """
        if self._container is None:
            return None
        with tempfile.NamedTemporaryFile(mode="r", suffix=".txt", delete=False) as f:
            tmp_path = f.name
        try:
            subprocess.run(
                ["docker", "cp", f"{self._container.id}:/tmp/worker-error.txt", tmp_path],
                check=True,
                capture_output=True,
                timeout=10,
            )
            with open(tmp_path, "r") as f:
                return f.read()
        except (OSError, subprocess.CalledProcessError):
            return None
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

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
        """Build the Worker image if it doesn't exist or code has changed.

        Tags each build with the current git HEAD hash. On subsequent
        calls, if the hash-tagged image already exists the build is
        skipped. After a merge to main (new hash), the image is
        automatically rebuilt — this is the ratchet mechanism.
        """
        git_hash = self._git_head_hash()
        version_tag = f"{self.config.worker_image}-{git_hash}" if git_hash else ""

        # Check if an image for this exact commit already exists.
        if version_tag:
            try:
                self._client.images.get(version_tag)
                log.debug("Worker image up to date: %s", version_tag)
                return
            except ImageNotFound:
                pass

        # Fall back to checking if the base image exists at all.
        try:
            self._client.images.get(self.config.worker_image)
            if not version_tag:
                log.debug("Worker image found (no git hash): %s", self.config.worker_image)
                return
            # Base image exists but is stale (wrong hash).
            log.info("Worker image stale, rebuilding for %s ...", git_hash)
        except ImageNotFound:
            log.info("Worker image not found, building %s ...", self.config.worker_image)

        self._client.images.build(
            path=".",
            dockerfile="worker/Dockerfile",
            tag=self.config.worker_image,
            rm=True,
        )
        # Also tag with the git hash so the next call skips the build.
        if version_tag:
            image = self._client.images.get(self.config.worker_image)
            image.tag(version_tag)
        log.info("Worker image built: %s (%s)", self.config.worker_image, git_hash or "no hash")

    @staticmethod
    def _git_head_hash() -> str:
        """Return the short hash of HEAD, or empty string on failure."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=10, check=True,
            )
            return result.stdout.strip()
        except Exception:
            return ""
