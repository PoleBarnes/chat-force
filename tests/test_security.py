"""Validate security configurations.

Tests cover:
  - exec-approvals.json structure and blocked commands
  - Audit logger write/read/scrub functionality
  - Secret pattern detection
  - Git pre-push hook existence
"""

import json
import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Add project root to sys.path so audit/ is importable as a top-level package
sys.path.insert(0, str(PROJECT_ROOT))

from audit.audit_logger import AuditLogger, AuditEventType
from audit.secret_patterns import scan_text, has_secrets, scrub_text, COMPILED_PATTERNS


# =========================================================================
# exec-approvals.json tests
# =========================================================================


class TestExecApprovals:
    """Test the exec-approvals.json configuration."""

    @pytest.fixture
    def exec_approvals(self):
        path = PROJECT_ROOT / "security" / "exec-approvals.json"
        assert path.exists(), "exec-approvals.json not found"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_exec_approvals_is_valid_json(self, exec_approvals):
        """exec-approvals.json must parse as a valid JSON object."""
        assert isinstance(exec_approvals, dict)

    def test_exec_approvals_has_required_structure(self, exec_approvals):
        """Must have allowed, blocked, and enforcement sections."""
        assert "allowed" in exec_approvals, "Missing 'allowed' section"
        assert "blocked" in exec_approvals, "Missing 'blocked' section"
        assert "enforcement" in exec_approvals, "Missing 'enforcement' section"

    def test_allowed_commands_have_structure(self, exec_approvals):
        """Each allowed command must have command and description."""
        for entry in exec_approvals["allowed"]:
            assert "command" in entry, f"Allowed entry missing 'command': {entry}"
            assert "description" in entry, f"Allowed entry missing 'description': {entry}"

    def test_blocked_patterns_have_structure(self, exec_approvals):
        """Each blocked pattern must have pattern and reason."""
        for entry in exec_approvals["blocked"]:
            assert "pattern" in entry, f"Blocked entry missing 'pattern': {entry}"
            assert "reason" in entry, f"Blocked entry missing 'reason': {entry}"

    def test_dangerous_commands_are_blocked(self, exec_approvals):
        """rm -rf, chmod, sudo, etc. must appear in the blocked list."""
        blocked_patterns = [b["pattern"].lower() for b in exec_approvals["blocked"]]
        dangerous = ["rm -rf", "chmod", "sudo", "kill", "shutdown"]
        for cmd in dangerous:
            found = any(cmd in pattern for pattern in blocked_patterns)
            assert found, f"Dangerous command '{cmd}' is not in blocked list"

    def test_force_push_is_blocked(self, exec_approvals):
        """Force push patterns must be blocked."""
        blocked_patterns = [b["pattern"] for b in exec_approvals["blocked"]]
        assert any("force" in p or "-f" in p for p in blocked_patterns), (
            "git push --force or -f not found in blocked patterns"
        )

    def test_main_branch_push_is_blocked(self, exec_approvals):
        """Pushing directly to main/master must be blocked."""
        blocked_patterns = [b["pattern"] for b in exec_approvals["blocked"]]
        assert any("main" in p and "push" in p for p in blocked_patterns), (
            "Direct push to main not found in blocked patterns"
        )

    def test_enforcement_is_deny_by_default(self, exec_approvals):
        """Default policy should be deny."""
        enforcement = exec_approvals.get("enforcement", {})
        assert enforcement.get("default_policy") == "deny", (
            "Enforcement default_policy should be 'deny'"
        )

    def test_self_modification_prevention(self, exec_approvals):
        """Must have self-modification prevention for config files."""
        smp = exec_approvals.get("self_modification_prevention")
        assert smp is not None, "Missing self_modification_prevention section"
        assert "protected_paths" in smp
        assert len(smp["protected_paths"]) > 0


# =========================================================================
# Audit logger tests
# =========================================================================


class TestAuditLogger:
    """Test the audit logger module."""

    @pytest.fixture
    def temp_log_dir(self, tmp_path):
        return str(tmp_path / "audit_logs")

    @pytest.fixture
    def audit_logger(self, temp_log_dir):
        return AuditLogger(workspace_id="test-workspace", log_dir=temp_log_dir)

    def test_audit_logger_writes_events(self, audit_logger):
        """AuditLogger must write events to log files."""
        event = audit_logger.log(
            AuditEventType.TASK_START,
            {"task": "test task", "input": "hello world"},
        )
        assert event["event_type"] == "task_start"
        assert event["workspace_id"] == "test-workspace"
        assert "timestamp" in event

    def test_audit_logger_reads_events(self, audit_logger):
        """AuditLogger must be able to read back written events."""
        audit_logger.log(AuditEventType.TASK_START, {"task": "test1"})
        audit_logger.log(AuditEventType.TASK_COMPLETE, {"task": "test1"})
        audit_logger.log(AuditEventType.TASK_START, {"task": "test2"})

        all_events = audit_logger.get_events()
        assert len(all_events) == 3

        starts = audit_logger.get_events(event_type=AuditEventType.TASK_START)
        assert len(starts) == 2

    def test_audit_logger_scrubs_secrets(self, audit_logger):
        """Secret patterns must be redacted when sensitive=True."""
        event = audit_logger.log(
            AuditEventType.LLM_CALL,
            {
                "api_key": "sk-ant-abc123def456ghi789jkl012",
                "token": "xoxb-123456-789012-abcdef",
                "model": "claude-opus-4-6",
                "prompt": "Hello world",
            },
            sensitive=True,
        )
        details = event["details"]
        assert details["api_key"] == "[REDACTED]", (
            f"api_key was not redacted: {details['api_key']}"
        )
        assert details["token"] == "[REDACTED]", (
            f"token was not redacted: {details['token']}"
        )
        assert details["model"] == "claude-opus-4-6"

    def test_audit_logger_scrubs_secrets_in_values(self, audit_logger):
        """Secret patterns in string values should be caught by regex."""
        event = audit_logger.log(
            AuditEventType.COMMAND_EXECUTED,
            {
                "command": "curl -H 'Authorization: bearer sk-ant-abcdefghijklmnopqrstuvwxyz'",
                "result": "some output",
            },
            sensitive=True,
        )
        details = event["details"]
        assert details["command"] == "[REDACTED]", (
            f"Command with secret was not redacted: {details['command']}"
        )

    def test_audit_logger_convenience_methods(self, audit_logger):
        """Convenience methods (log_command_blocked, etc.) should work."""
        event = audit_logger.log_command_blocked("rm -rf /", "Recursive deletion blocked")
        assert event["event_type"] == "command_blocked"
        assert event["details"]["command"] == "rm -rf /"

        event = audit_logger.log_command_executed("ls -la", exit_code=0)
        assert event["event_type"] == "command_executed"

        event = audit_logger.log_secret_access("ANTHROPIC_AUTH_TOKEN", "LLM call")
        assert event["event_type"] == "secret_access"

    def test_audit_logger_log_rotation(self, audit_logger, temp_log_dir):
        """Log rotation should delete old files."""
        log_dir = Path(temp_log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        old_file = log_dir / "2020-01-01.jsonl"
        old_file.write_text('{"test": "old"}\n')

        audit_logger.log(AuditEventType.TASK_START, {"task": "recent"})

        deleted = audit_logger.rotate_logs()
        assert deleted >= 1, "Expected at least 1 old file to be deleted"
        assert not old_file.exists(), "Old log file should have been deleted"


# =========================================================================
# Secret patterns tests
# =========================================================================


class TestSecretPatterns:
    """Test the secret detection patterns module."""

    def test_detect_anthropic_key(self):
        """Must detect Anthropic API key format."""
        text = "My key is sk-ant-abcdefghijklmnopqrstuvwxyz"
        assert has_secrets(text, min_severity="critical")
        findings = scan_text(text)
        assert len(findings) >= 1
        assert any("Anthropic" in f["pattern_name"] for f in findings)

    def test_detect_slack_bot_token(self):
        """Must detect Slack bot token format."""
        text = "SLACK_TOKEN=xoxb-123456789012-123456789012-abcdefghij"
        assert has_secrets(text, min_severity="critical")

    def test_detect_github_pat(self):
        """Must detect GitHub Personal Access Token."""
        text = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh12"
        assert has_secrets(text, min_severity="critical")

    def test_detect_doppler_service_token(self):
        """Must detect Doppler service token."""
        text = "dp.st.some-project_some-env_some-token-value"
        assert has_secrets(text, min_severity="critical")

    def test_detect_private_key(self):
        """Must detect PEM private key headers."""
        text = "-----BEGIN RSA PRIVATE KEY-----\nfoo"
        assert has_secrets(text, min_severity="critical")

    def test_no_false_positive_on_normal_text(self):
        """Normal text should not trigger secret detection."""
        text = "This is a normal message about building a campaign for BlackTie."
        assert not has_secrets(text, min_severity="high")

    def test_scrub_text_replaces_secrets(self):
        """scrub_text should replace detected secrets with [REDACTED]."""
        text = "API key: sk-ant-abcdefghijklmnopqrstuvwxyz and more text"
        scrubbed = scrub_text(text)
        assert "sk-ant" not in scrubbed
        assert "[REDACTED]" in scrubbed
        assert "and more text" in scrubbed

    def test_all_patterns_compile(self):
        """All patterns in COMPILED_PATTERNS should be valid compiled regexes."""
        assert len(COMPILED_PATTERNS) >= 15, (
            f"Expected at least 15 patterns, found {len(COMPILED_PATTERNS)}"
        )
        for pattern, name, severity in COMPILED_PATTERNS:
            assert isinstance(pattern, re.Pattern), (
                f"Pattern '{name}' is not compiled"
            )
            assert severity in ("critical", "high", "medium"), (
                f"Pattern '{name}' has invalid severity: {severity}"
            )


# =========================================================================
# Git hook tests
# =========================================================================


class TestGitHook:
    """Test the git pre-push hook script."""

    def test_git_hook_script_exists(self):
        """The pre-push hook script must be present."""
        hook_path = PROJECT_ROOT / "scripts" / "git-pre-push-hook.sh"
        assert hook_path.exists(), "scripts/git-pre-push-hook.sh not found"

    def test_git_hook_has_shebang(self):
        """The hook script must start with a proper shebang."""
        hook_path = PROJECT_ROOT / "scripts" / "git-pre-push-hook.sh"
        first_line = hook_path.read_text(encoding="utf-8").split("\n")[0]
        assert first_line.startswith("#!/"), (
            f"Hook script missing shebang, starts with: {first_line}"
        )

    def test_git_hook_references_patterns(self):
        """The hook script should reference the canonical secret_patterns module."""
        hook_path = PROJECT_ROOT / "scripts" / "git-pre-push-hook.sh"
        content = hook_path.read_text(encoding="utf-8")
        assert "secret_patterns" in content, (
            "Hook script does not reference secret_patterns module"
        )

    def test_git_hook_has_fallback_patterns(self):
        """The hook script should include grep-based fallback patterns."""
        hook_path = PROJECT_ROOT / "scripts" / "git-pre-push-hook.sh"
        content = hook_path.read_text(encoding="utf-8")
        assert "FALLBACK_PATTERNS" in content, (
            "Hook script missing FALLBACK_PATTERNS for grep fallback"
        )
