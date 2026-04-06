"""Host-side Mechanic evaluation via the Agent SDK."""

import asyncio
import json
import logging
import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pipeline.config import PipelineConfig

log = logging.getLogger(__name__)

_DEFAULT_MECHANIC_SYSTEM_PROMPT = (
    "You are the Mechanic — a code reviewer for the Digital Workforce Platform. "
    "Evaluate the changeset and return ONLY a JSON object (no markdown, no explanation) "
    "with these fields:\n"
    "- verdict: 'approve' or 'reject'\n"
    "- pr_title: short title for the PR\n"
    "- pr_body: description for the PR body\n"
    "- files_to_include: list of file paths that should be in the PR (from git_changes)\n"
    "- confidence: 'high', 'medium', or 'low'\n"
    "- evaluation: summary of what you found\n"
    "If rejecting, also include:\n"
    "- reason: why you are rejecting\n"
    "- feedback: list of specific items to fix\n"
    "- disposition: 'iterate' (send feedback to worker), 'discard' (abandon), "
    "or 'linear_issue' (create a ticket)\n"
    "If previous_rejections are present, check whether the worker addressed the feedback."
)

_MECHANIC_CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "mechanic", "config")


def _build_mechanic_system_prompt() -> str:
    sections = []
    config_dir = os.path.normpath(_MECHANIC_CONFIG_DIR)
    for name in ("SOUL", "IDENTITY", "AGENTS"):
        path = os.path.join(config_dir, f"{name}.md")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().rstrip()
            sections.append(f"# {name}\n{content}\n\n")
    if not sections:
        return _DEFAULT_MECHANIC_SYSTEM_PROMPT
    return "".join(sections)


class EvaluationCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pass_: bool = Field(alias="pass")
    notes: str


class Evaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    meaningful: EvaluationCriterion
    correct: EvaluationCriterion
    safe: EvaluationCriterion
    minimal: EvaluationCriterion
    reproducible: EvaluationCriterion


class MechanicVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict: Literal["approve", "reject"]
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    evaluation: Evaluation
    feedback: list[str]
    disposition: Literal["pr", "linear_issue", "discard"]
    disposition_reason: str
    pr_title: str
    pr_body: str
    files_to_include: list[str]
    files_to_exclude: list[str]
    rejection_reason: str


VERDICT_SCHEMA = MechanicVerdict.model_json_schema()


class MechanicParseError(Exception):
    """Raised when the Mechanic's verdict cannot be parsed or validated.

    This is a distinct error state — NOT a rejection. It means the Mechanic
    itself malfunctioned, not that the Worker's code was bad.
    """


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
        prompt = self._build_evaluation_prompt(changeset_json)
        verdict = self._run_query(prompt, changeset_json)
        return self._validate_verdict(verdict)

    def cleanup(self) -> None:
        pass

    # -- internals ------------------------------------------------------------

    def _run_query(self, prompt: str, changeset_json: str) -> dict:
        """Run a single Mechanic evaluation turn and parse the JSON verdict."""
        from claude_agent_sdk import query, ClaudeAgentOptions

        async def _collect_result_text() -> dict | str:
            result_text = ""
            assistant_text_parts: list[str] = []

            # max_turns=5 allows structured output to complete — the model
            # typically responds normally first, then the Stop hook prompts
            # it to call the StructuredOutput tool on a subsequent turn.
            opts = ClaudeAgentOptions(
                system_prompt=_build_mechanic_system_prompt(),
                max_turns=5,
                permission_mode="plan",
                output_format={"type": "json_schema", "schema": VERDICT_SCHEMA},
            )
            async for message in query(prompt=prompt, options=opts):
                message_type = type(message).__name__

                if message_type == "AssistantMessage":
                    content = getattr(message, "content", []) or []
                    for block in content:
                        text = getattr(block, "text", None)
                        if isinstance(text, str) and text:
                            assistant_text_parts.append(text)
                    continue

                if message_type == "ResultMessage":
                    structured = getattr(message, "structured_output", None)
                    if isinstance(structured, dict):
                        return structured
                    text = getattr(message, "result", None)
                    if isinstance(text, str) and text:
                        result_text = text

            return result_text or "".join(assistant_text_parts)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            result = asyncio.run(_collect_result_text())
        else:
            import threading

            runner_result: dict[str, dict | str] = {}
            runner_error: list[BaseException] = []

            def _thread_runner() -> None:
                try:
                    runner_result["text"] = asyncio.run(_collect_result_text())
                except BaseException as exc:  # pragma: no cover - defensive thread handoff
                    runner_error.append(exc)

            thread = threading.Thread(target=_thread_runner)
            thread.start()
            thread.join(timeout=self.config.mechanic_timeout)
            if thread.is_alive():
                raise TimeoutError(
                    f"Mechanic evaluation timed out after {self.config.mechanic_timeout}s"
                )
            if runner_error:
                raise runner_error[0]
            result = runner_result.get("text", "")

        if isinstance(result, dict):
            return result
        try:
            return json.loads(result)
        except (TypeError, json.JSONDecodeError) as exc:
            raise MechanicParseError(
                f"Mechanic verdict was not valid JSON for run {self.run_id}: {exc}"
            ) from exc

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
            elif "/harness/" in path:
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

        result = {
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

        previous = changeset.get("previous_rejections")
        if previous:
            result["previous_rejections"] = previous

        return result

    def _build_evaluation_prompt(self, changeset_json: str) -> str:
        """Build the Mechanic prompt, including harness eval criteria when available.

        Each check is serialized with every field that carries evaluation
        semantics (``id``, ``description``, ``type``, ``pattern``,
        ``must_not_match``). Dropping any of these would reduce a mechanical
        check like ``{type: regex, pattern: "!", must_not_match: true}`` to
        bare prose with no executable meaning, which defeats the purpose of
        plumbing eval criteria through at all.
        """
        if self.config.harness is None:
            return "Evaluate this changeset and return your verdict as JSON:\n\n" + changeset_json

        criteria = self.config.harness.eval_criteria
        parts = [
            "# Customer Eval Criteria",
            criteria.narrative.strip(),
            "",
            "## Checklist",
        ]

        if criteria.checks:
            for check in criteria.checks:
                check_data = check.model_dump(exclude_none=True)
                parts.append(f"- {check.id} ({check.type}): {check.description}")
                for field_name, field_value in check_data.items():
                    if field_name in ("id", "type", "description"):
                        continue
                    parts.append(f"    {field_name}: {field_value!r}")
        else:
            parts.append("- No additional checklist items provided.")

        parts.extend(
            [
                "",
                "# Changeset",
                changeset_json,
            ]
        )
        return "\n".join(parts)

    @staticmethod
    def _validate_verdict(verdict: dict) -> dict:
        """Validate the verdict and normalise it for pipeline consumers."""
        try:
            validated = MechanicVerdict.model_validate(verdict)
        except ValidationError as exc:
            raise MechanicParseError(
                f"Mechanic verdict failed validation: {exc.errors()[0]['msg']}"
            ) from exc

        result = validated.model_dump(by_alias=True)
        result["approved"] = validated.verdict == "approve"
        if not result["approved"]:
            result["reason"] = validated.rejection_reason or "No reason provided"

        return result
