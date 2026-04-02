"""Audit logger for the Digital Workforce Platform.

All agent actions are logged with structured JSON for:
- Compliance tracking
- Mechanic analysis
- Security auditing
- Cost tracking

Logs are written to audit/logs/ directory as daily JSONL files.
Each line is a self-contained JSON object for easy streaming and analysis.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path

from .secret_patterns import COMPILED_PATTERNS


class AuditEventType(Enum):
    """All auditable event types in the platform."""
    TASK_START = "task_start"
    TASK_COMPLETE = "task_complete"
    TASK_ERROR = "task_error"
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    APPROVAL_REQUEST = "approval_request"
    APPROVAL_DECISION = "approval_decision"
    MECHANIC_PROPOSAL = "mechanic_proposal"
    MECHANIC_DECISION = "mechanic_decision"
    SECRET_ACCESS = "secret_access"
    COMMAND_BLOCKED = "command_blocked"
    COMMAND_EXECUTED = "command_executed"
    CONFIG_CHANGE = "config_change"
    SOP_EXECUTION = "sop_execution"


# Keys in detail dicts that may contain sensitive values
_SENSITIVE_KEYS = frozenset({
    'token', 'key', 'secret', 'password', 'credential', 'authorization',
    'api_key', 'api_secret', 'access_token', 'refresh_token', 'private_key',
    'client_secret', 'webhook_secret', 'signing_secret',
})


class AuditLogger:
    """Thread-safe structured audit logger.

    Writes JSON-lines to daily log files under the configured log directory.
    Automatically scrubs secrets from log entries when sensitive=True.
    Rotates logs by deleting files older than retention_days.
    """

    def __init__(
        self,
        workspace_id: str,
        log_dir: str | None = None,
        retention_days: int = 90,
    ):
        self.workspace_id = workspace_id
        self.retention_days = retention_days
        self._lock = threading.Lock()

        if log_dir is None:
            # Default: audit/logs/ relative to this file
            self._log_dir = Path(__file__).parent / "logs"
        else:
            self._log_dir = Path(log_dir)

        self._log_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log(
        self,
        event_type: AuditEventType,
        details: dict,
        sensitive: bool = True,
    ) -> dict:
        """Log an audit event.

        Args:
            event_type: The category of event being logged.
            details: Arbitrary dict of event-specific data.
            sensitive: If True, scrub any potential secrets from details
                       before writing to disk.

        Returns:
            The full event dict that was written (useful for testing).
        """
        now = datetime.now(timezone.utc)

        safe_details = self._scrub_secrets(details) if sensitive else details

        event = {
            "timestamp": now.isoformat(),
            "event_type": event_type.value,
            "workspace_id": self.workspace_id,
            "details": safe_details,
            "scrubbed": sensitive,
        }

        log_file = self._log_dir / f"{now.strftime('%Y-%m-%d')}.jsonl"

        with self._lock:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, default=str) + "\n")

        return event

    def get_events(
        self,
        event_type: AuditEventType | None = None,
        since: datetime | None = None,
        limit: int = 1000,
    ) -> list[dict]:
        """Query audit events from log files.

        Args:
            event_type: Filter to only this event type (None = all).
            since: Only return events after this timestamp (None = all time).
            limit: Maximum number of events to return.

        Returns:
            List of event dicts, most recent first.
        """
        events: list[dict] = []

        # Determine which files to read based on the 'since' filter
        log_files = sorted(self._log_dir.glob("*.jsonl"), reverse=True)

        if since is not None:
            cutoff_date = since.strftime("%Y-%m-%d")
        else:
            cutoff_date = None

        for log_file in log_files:
            file_date = log_file.stem  # e.g. "2026-04-01"

            # Skip files older than the cutoff date
            if cutoff_date and file_date < cutoff_date:
                break

            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        # Apply event_type filter
                        if event_type is not None and event.get("event_type") != event_type.value:
                            continue

                        # Apply since filter
                        if since is not None:
                            event_ts = datetime.fromisoformat(event["timestamp"])
                            if event_ts < since:
                                continue

                        events.append(event)
            except OSError:
                continue

        # Sort by timestamp descending and apply limit
        events.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        return events[:limit]

    def rotate_logs(self) -> int:
        """Delete log files older than retention_days.

        Returns:
            Number of files deleted.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        cutoff_str = cutoff.strftime("%Y-%m-%d")
        deleted = 0

        for log_file in self._log_dir.glob("*.jsonl"):
            if log_file.stem < cutoff_str:
                try:
                    log_file.unlink()
                    deleted += 1
                except OSError:
                    pass

        return deleted

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def log_command_blocked(self, command: str, reason: str) -> dict:
        """Shorthand for logging a blocked command."""
        return self.log(AuditEventType.COMMAND_BLOCKED, {
            "command": command,
            "reason": reason,
        })

    def log_command_executed(self, command: str, exit_code: int = 0) -> dict:
        """Shorthand for logging a successfully executed command."""
        return self.log(AuditEventType.COMMAND_EXECUTED, {
            "command": command,
            "exit_code": exit_code,
        })

    def log_secret_access(self, secret_name: str, purpose: str) -> dict:
        """Log that a secret was accessed, without logging the value."""
        return self.log(AuditEventType.SECRET_ACCESS, {
            "secret_name": secret_name,
            "purpose": purpose,
            "note": "Secret value not logged — only access event recorded.",
        })

    def log_llm_call(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float | None = None,
        purpose: str = "",
    ) -> dict:
        """Log an LLM API call for cost tracking."""
        return self.log(AuditEventType.LLM_CALL, {
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
            "purpose": purpose,
        })

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _scrub_secrets(self, data: dict) -> dict:
        """Remove any values that look like secrets from a dict.

        Two-pass approach:
        1. Scrub values whose keys look sensitive (token, key, secret, etc.)
        2. Scrub string values that match known secret regex patterns
        """
        scrubbed = {}
        for key, value in data.items():
            if isinstance(value, dict):
                scrubbed[key] = self._scrub_secrets(value)
            elif isinstance(value, list):
                scrubbed[key] = [
                    self._scrub_secrets(item) if isinstance(item, dict)
                    else self._scrub_value(key, item)
                    for item in value
                ]
            else:
                scrubbed[key] = self._scrub_value(key, value)
        return scrubbed

    def _scrub_value(self, key: str, value: object) -> object:
        """Scrub a single value if the key or content indicates a secret."""
        # Check if the key name suggests a secret
        key_lower = key.lower().replace("-", "_")
        if any(sensitive_key in key_lower for sensitive_key in _SENSITIVE_KEYS):
            return "[REDACTED]"

        # Check string values against regex patterns
        if isinstance(value, str):
            for pattern, _name, _severity in COMPILED_PATTERNS:
                if pattern.search(value):
                    return "[REDACTED]"

        return value
