"""Host-side Mechanic evaluation via the Agent SDK."""

import asyncio
import json
import logging

from pipeline.config import PipelineConfig

log = logging.getLogger(__name__)

_DEFAULT_MECHANIC_SYSTEM_PROMPT = (
    "You are the Mechanic — a code reviewer for the Digital Workforce Platform. "
    "Evaluate the changeset and return a JSON verdict with these fields: verdict "
    "(approve/reject), pr_title, confidence (high/medium/low), reason (if "
    "rejecting), evaluation (summary of what you found)."
)


class MechanicManager:
    """Evaluates changesets with the Mechanic via the Agent SDK."""

    def __init__(self, config: PipelineConfig, run_id: str):
        self.config = config
        self.run_id = run_id

    # -- public API -----------------------------------------------------------

    def evaluate(self, changeset: dict) -> dict:
        """Run the Mechanic on *changeset* and return the parsed verdict."""
        evaluation = self._prepare_evaluation(changeset)
        changeset_json = json.dumps(evaluation, indent=2)
        prompt = "Evaluate this changeset and return your verdict as JSON:\n\n" + changeset_json
        verdict = self._run_query(prompt, changeset_json)
        return self._validate_verdict(verdict)

    def cleanup(self) -> None:
        pass

    # -- internals ------------------------------------------------------------

    def _run_query(self, prompt: str, changeset_json: str) -> dict:
        """Run a single Mechanic evaluation turn and parse the JSON verdict."""
        from claude_agent_sdk import query, ClaudeAgentOptions

        async def _collect_result_text() -> str:
            result_text = ""
            assistant_text_parts: list[str] = []

            opts = ClaudeAgentOptions(
                system_prompt=_DEFAULT_MECHANIC_SYSTEM_PROMPT,
                max_turns=1,
                permission_mode="plan",
            )
            async for message in query(prompt=prompt, options=opts):
                message_type = type(message).__name__

                if message_type == "AssistantMessage":
                    content = getattr(message, "content", []) or []
                    for block in content:
                        if getattr(block, "type", None) == "text":
                            text = getattr(block, "text", None)
                            if isinstance(text, str) and text:
                                assistant_text_parts.append(text)
                    continue

                if message_type == "ResultMessage":
                    text = getattr(message, "result", None)
                    if isinstance(text, str) and text:
                        result_text = text

            return result_text or "".join(assistant_text_parts)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            result_text = asyncio.run(_collect_result_text())
        else:
            import threading

            runner_result: dict[str, str] = {}
            runner_error: list[BaseException] = []

            def _thread_runner() -> None:
                try:
                    runner_result["text"] = asyncio.run(_collect_result_text())
                except BaseException as exc:  # pragma: no cover - defensive thread handoff
                    runner_error.append(exc)

            thread = threading.Thread(target=_thread_runner)
            thread.start()
            thread.join()
            if runner_error:
                raise runner_error[0]
            result_text = runner_result.get("text", "")

        try:
            return json.loads(result_text)
        except (TypeError, json.JSONDecodeError):
            log.warning(
                "Mechanic verdict was not valid JSON for run %s (payload size=%d chars)",
                self.run_id,
                len(changeset_json),
            )
            return {"approved": False, "reason": "Failed to parse verdict"}

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

        # ── Git changes: strip binary/large files from file_contents ──
        # The Mechanic reviews source code, not binary blobs or lock files.
        BINARY_EXTENSIONS = {
            ".mp4", ".webm", ".mov", ".avi", ".mp3", ".wav", ".ogg", ".flac",
            ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
            ".pdf", ".zip", ".tar", ".gz", ".woff", ".woff2", ".ttf", ".eot",
        }
        SKIP_FILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml"}
        MAX_FILE_SIZE = 50_000  # 50K chars — skip anything bigger

        filtered_contents = {}
        skipped_files = []
        for path, content in git.get("file_contents", {}).items():
            basename = path.rsplit("/", 1)[-1] if "/" in path else path
            ext = ("." + basename.rsplit(".", 1)[-1]).lower() if "." in basename else ""
            if basename in SKIP_FILES:
                skipped_files.append(f"{path} (lock file, {len(content):,} chars)")
            elif ext in BINARY_EXTENSIONS:
                skipped_files.append(f"{path} (binary, {len(content):,} chars)")
            elif len(content) > MAX_FILE_SIZE:
                skipped_files.append(f"{path} (too large, {len(content):,} chars)")
            else:
                filtered_contents[path] = content

        git_for_review = dict(git)
        git_for_review["file_contents"] = filtered_contents
        if skipped_files:
            git_for_review["skipped_files"] = skipped_files

        return {
            "run_id": changeset.get("run_id"),
            "task": changeset.get("task"),
            "timestamp": changeset.get("timestamp"),
            "git_changes": git_for_review,
            "docker_changes_summary": docker_summary,
            "telemetry": telemetry_summary,
            "output_files": output_summary,
            "tool_log": changeset.get("tool_log", []),
            "usage": changeset.get("usage", {}),
            "memory_changes": changeset.get("memory_changes", []),
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
