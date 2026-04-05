"""Extract what a Worker container actually changed -- the ground truth.

Runs from the HOST, reaching into the container via docker exec / docker cp.
Assembles a JSON changeset bundle across four layers:

  1. Git diff    -- config/skill file changes in /harness
  2. Docker diff -- filesystem changes visible to the Docker storage driver
  3. Telemetry   -- exit code, timestamps, container logs
  4. Agent SDK   -- tool log (JSONL), usage data, response text
"""

import fnmatch
import json
import logging
import os
import subprocess
from datetime import datetime, timezone

import docker
from docker.errors import NotFound

from pipeline.config import PipelineConfig

log = logging.getLogger(__name__)

NOISE_PATTERNS = [
    "/tmp/",
    "/var/log/",
    "/var/cache/",
    "/root/.cache/",
    "/home/node/.npm/",
    "/home/node/.cache/",
    "*.pyc",
    "__pycache__",
    ".git/",
]

# How many log lines to capture from the container.
_LOG_TAIL_LINES = 500
WORKER_CWD = "/harness"


def _is_noise(path: str) -> bool:
    """Return True if *path* matches any noise pattern."""
    for pat in NOISE_PATTERNS:
        # Directory prefix patterns (end with /)
        if pat.endswith("/") and pat in path:
            return True
        # Substring patterns (no glob chars)
        if "*" not in pat and "?" not in pat and pat in path:
            return True
        # Glob patterns
        if fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(os.path.basename(path), pat):
            return True
    return False


class ChangesetExtractor:
    """Extracts everything a Worker container changed and writes a changeset bundle."""

    def __init__(self, config: PipelineConfig, run_id: str):
        self.config = config
        self.run_id = run_id
        self.client = docker.from_env()
        self.run_dir = os.path.join(config.output_base, run_id)
        os.makedirs(self.run_dir, exist_ok=True)

    # -- public API -----------------------------------------------------------

    def extract(self, container_id: str, task: str = "") -> dict:
        """Run all extraction layers and return the changeset bundle."""
        bundle = {
            "run_id": self.run_id,
            "task": task,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "worker_container": container_id,
        }

        container = self._get_container(container_id)

        bundle["git_changes"] = self._extract_git_changes(container)
        bundle["docker_changes"] = self._extract_docker_changes(container)
        bundle["telemetry"] = self._extract_telemetry(container)
        bundle["agent_logs"] = self._extract_agent_logs(container, container_id)
        bundle["tool_log"] = self._parse_tool_log(bundle["agent_logs"].get("tool_log_path"))
        bundle["usage"] = self._parse_usage(bundle["agent_logs"].get("usage_path"))
        bundle["output_files"] = self._extract_output_files(container, container_id)
        bundle["bundle_path"] = self.run_dir

        self._save_bundle(bundle)
        return bundle

    # -- Layer 1: Git diff ----------------------------------------------------

    def _extract_git_changes(self, container) -> dict:
        """Capture git diff, status, and full content of changed/new files."""
        result = {
            "diff": "",
            "status": "",
            "new_files": [],
            "modified_files": [],
            "deleted_files": [],
            "file_contents": {},
        }

        try:
            result["diff"] = self._exec(container, f"cd {WORKER_CWD} && git diff")
            result["status"] = self._exec(container, f"cd {WORKER_CWD} && git status --porcelain")

            untracked_raw = self._exec(
                container,
                f"cd {WORKER_CWD} && git ls-files --others --exclude-standard",
            )
            changed_raw = self._exec(
                container,
                f"cd {WORKER_CWD} && git diff --name-only",
            )

            # Parse file lists
            result["new_files"] = _nonempty_lines(untracked_raw)
            result["modified_files"] = _nonempty_lines(changed_raw)

            # Deleted files come from porcelain status lines starting with " D" or "D "
            for line in _nonempty_lines(result["status"]):
                code = line[:2]
                path = line[3:]
                if "D" in code:
                    result["deleted_files"].append(path)

            # Grab full content of every changed or new file
            all_interesting = result["new_files"] + result["modified_files"]
            for fpath in all_interesting:
                try:
                    content = self._exec(
                        container,
                        f"cat {WORKER_CWD}/{fpath}",
                    )
                    result["file_contents"][fpath] = content
                except Exception:
                    log.debug("Could not read file content for %s", fpath)

        except Exception:
            log.warning("Layer 1 (git changes) failed", exc_info=True)

        return result

    # -- Layer 2: Docker diff -------------------------------------------------

    def _extract_docker_changes(self, container) -> dict:
        """Use the Docker API to list filesystem changes in the container."""
        result = {
            "added": [],
            "changed": [],
            "deleted": [],
            "filtered_noise": [],
        }

        try:
            changes = container.diff()
            if changes is None:
                return result

            # Docker diff returns list of {"Path": str, "Kind": int}
            # Kind: 0=Modified, 1=Added, 2=Deleted
            kind_map = {0: "changed", 1: "added", 2: "deleted"}

            for entry in changes:
                path = entry["Path"]
                kind = kind_map.get(entry["Kind"], "changed")

                if _is_noise(path):
                    result["filtered_noise"].append(path)
                    continue

                result[kind].append(path)

        except Exception:
            log.warning("Layer 2 (docker diff) failed", exc_info=True)

        return result

    # -- Layer 3: Execution telemetry -----------------------------------------

    def _extract_telemetry(self, container) -> dict:
        """Capture exit code, timing, and tail of container logs."""
        result = {
            "exit_code": None,
            "started_at": None,
            "finished_at": None,
            "duration_seconds": None,
            "container_logs": "",
        }

        try:
            container.reload()
            state = container.attrs.get("State", {})

            result["exit_code"] = state.get("ExitCode")
            result["started_at"] = state.get("StartedAt")
            result["finished_at"] = state.get("FinishedAt")

            # Calculate duration
            started = state.get("StartedAt", "")
            finished = state.get("FinishedAt", "")
            if started and finished:
                try:
                    t_start = _parse_docker_ts(started)
                    t_end = _parse_docker_ts(finished)
                    if t_start and t_end:
                        result["duration_seconds"] = round(
                            (t_end - t_start).total_seconds()
                        )
                except Exception:
                    log.debug("Could not compute duration", exc_info=True)

            # Container logs
            result["container_logs"] = container.logs(
                tail=_LOG_TAIL_LINES
            ).decode(errors="replace")

        except Exception:
            log.warning("Layer 3 (telemetry) failed", exc_info=True)

        return result

    # -- Layer 4: Agent SDK logs -----------------------------------------------

    def _extract_agent_logs(self, container, container_id: str) -> dict:
        """Copy Agent SDK tool log, usage data, and response from the container."""
        tool_log_path = os.path.join(self.run_dir, "tool-log.jsonl")
        usage_path = os.path.join(self.run_dir, "usage.json")
        response_path = os.path.join(self.run_dir, "latest-response.txt")

        result = {
            "tool_log_path": None,
            "usage_path": None,
            "response_path": None,
        }

        if self._docker_cp(container_id, "/tmp/tool-log.jsonl", tool_log_path):
            result["tool_log_path"] = tool_log_path

        if self._docker_cp(container_id, "/tmp/usage.json", usage_path):
            result["usage_path"] = usage_path

        if self._docker_cp(container_id, "/tmp/latest-response.txt", response_path):
            result["response_path"] = response_path

        return result

    def _parse_tool_log(self, path: str | None) -> list[dict]:
        """Parse tool-log.jsonl from disk into a list of dicts."""
        if not path or not os.path.exists(path):
            return []
        try:
            with open(path, "r") as f:
                return [json.loads(line) for line in f if line.strip()]
        except (OSError, json.JSONDecodeError):
            log.warning("Could not parse tool log at %s", path)
            return []

    def _parse_usage(self, path: str | None) -> dict:
        """Parse usage.json from disk into a dict."""
        if not path or not os.path.exists(path):
            return {}
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            log.warning("Could not parse usage at %s", path)
            return {}

    # -- Layer 5: Output files (binaries, rendered artifacts) -----------------

    # File extensions that indicate rendered output worth preserving.
    _OUTPUT_EXTENSIONS = {
        ".mp4", ".webm", ".mov", ".avi",  # video
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",  # images
        ".pdf",  # documents
        ".zip", ".tar.gz",  # archives
    }

    def _extract_output_files(self, container, container_id: str) -> dict:
        """Copy binary/rendered output files from the container.

        Scans docker diff for files with known output extensions and copies
        them to the run directory so they survive container cleanup.
        """
        output_dir = os.path.join(self.run_dir, "output-files")
        copied = []

        try:
            diff = container.diff() or []
            for entry in diff:
                path = entry.get("Path", "")
                # Only copy added/changed files (not deleted), skip noise
                if entry.get("Kind", 0) not in (0, 1):  # 0=changed, 1=added
                    continue
                if _is_noise(path):
                    continue
                # Skip library/dependency internals
                if "/node_modules/" in path:
                    continue
                # Check if it's an output file worth preserving
                lower = path.lower()
                if any(lower.endswith(ext) for ext in self._OUTPUT_EXTENSIONS):
                    dest = os.path.join(output_dir, os.path.basename(path))
                    if self._docker_cp(container_id, path, dest):
                        copied.append({"container_path": path, "local_path": dest})
                        log.info("Captured output file: %s -> %s", path, dest)
        except Exception:
            log.warning("Failed to extract output files", exc_info=True)

        return {"output_dir": output_dir if copied else None, "files": copied}

    # -- helpers --------------------------------------------------------------

    def _get_container(self, container_id: str):
        """Return a Docker container object, or raise."""
        try:
            return self.client.containers.get(container_id)
        except NotFound:
            raise ValueError(
                f"Container {container_id[:12]} not found. "
                "Was it removed before changeset extraction?"
            )

    def _exec(self, container, cmd: str) -> str:
        """Run a command inside the container and return stdout as a string.

        Raises on non-zero exit code so the caller's try/except can handle it.
        """
        exit_code, output = container.exec_run(
            ["bash", "-c", cmd],
            demux=False,
        )
        text = output.decode(errors="replace") if output else ""
        if exit_code != 0:
            log.debug("exec_run returned %d for: %s\n%s", exit_code, cmd, text[:500])
        return text

    def _docker_cp(self, container_id: str, src: str, dst: str) -> bool:
        """Copy *src* from the container to *dst* on the host via `docker cp`.

        Returns True on success, False if the path didn't exist or copy failed.
        The Docker SDK doesn't expose a clean cp interface, so we shell out.
        """
        os.makedirs(os.path.dirname(dst) or dst, exist_ok=True)
        try:
            subprocess.run(
                ["docker", "cp", f"{container_id}:{src}", dst],
                check=True,
                capture_output=True,
                timeout=30,
            )
            log.debug("docker cp %s:%s -> %s", container_id[:12], src, dst)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            log.debug("docker cp failed for %s: %s", src, exc)
            return False

    def _save_bundle(self, bundle: dict) -> None:
        """Write the changeset bundle to disk as JSON."""
        path = os.path.join(self.run_dir, "changeset.json")
        with open(path, "w") as f:
            json.dump(bundle, f, indent=2, default=str)
        log.info("Changeset bundle written to %s", path)


# -- module-level helpers -----------------------------------------------------


def _nonempty_lines(text: str) -> list[str]:
    """Split text on newlines and discard blanks."""
    return [line for line in text.splitlines() if line.strip()]


def _parse_docker_ts(ts: str) -> datetime | None:
    """Parse a Docker timestamp (ISO 8601 with possible nanosecond precision).

    Docker often returns timestamps like '2026-04-01T14:30:22.123456789Z'.
    Python's fromisoformat can't handle >6 fractional digits, so we truncate.
    """
    if not ts or ts == "0001-01-01T00:00:00Z":
        return None

    # Normalise trailing Z to +00:00 for fromisoformat
    ts = ts.replace("Z", "+00:00")

    # Truncate nanoseconds to microseconds
    if "." in ts:
        dot_idx = ts.index(".")
        # Find where the fractional part ends (start of tz offset)
        frac_end = dot_idx + 1
        while frac_end < len(ts) and ts[frac_end].isdigit():
            frac_end += 1
        frac_digits = ts[dot_idx + 1 : frac_end]
        tz_suffix = ts[frac_end:]
        frac_digits = frac_digits[:6].ljust(6, "0")  # pad/truncate to 6
        ts = f"{ts[:dot_idx]}.{frac_digits}{tz_suffix}"

    return datetime.fromisoformat(ts)
