"""Session lifecycle manager for multi-message Slack conversations.

A session binds a Slack user to a single long-lived Worker container.
Messages flow into the container via WorkerManager.send_message(); the
container stays alive until the conversation goes idle for
`config.session_idle_timeout` seconds.  When the session closes, the
Mechanic evaluates the changeset and a PR is created if approved.

Thread-safe: multiple Slack messages can arrive concurrently.
"""

import json
import logging
import os
import secrets
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pipeline.changeset_extractor import ChangesetExtractor
from pipeline.config import PipelineConfig
from pipeline.main import _format_feedback, MAX_ITERATIONS
from pipeline.mechanic_manager import MechanicManager
from pipeline.pr_creator import PRCreator
from pipeline.webhook_server import WebhookServer
from pipeline.worker_manager import WorkerManager

log = logging.getLogger(__name__)

# How often the idle-checker thread wakes up (seconds).
_IDLE_CHECK_INTERVAL = 30


def _generate_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{ts}-{secrets.token_hex(4)}"


def _git_short_hash(run_id: str = "") -> str:
    """Return the short hash of HEAD on the current branch.

    If git fails or returns an empty string, falls back to the first 7
    characters of *run_id* so we always return a meaningful identifier.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        sha = result.stdout.strip()
        if sha:
            return sha
    except Exception:
        log.warning("Could not determine git short hash", exc_info=True)

    # Fallback: first 7 chars of the run_id (or a static token if run_id is empty).
    return run_id[:7] if run_id else "0000000"


# ---------------------------------------------------------------------------
# Session dataclass
# ---------------------------------------------------------------------------

@dataclass
class Session:
    """A live conversation between a Slack user and a Worker container."""

    user_id: str
    channel_id: str
    run_id: str
    container_id: str
    worker: WorkerManager
    created_at: datetime
    last_activity: datetime
    message_count: int = 0
    sandbox_version: str = ""
    _first_message: str = field(default="", repr=False)
    _ready: threading.Event = field(default_factory=threading.Event, repr=False)


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------

class SessionManager:
    """Manages the lifecycle of user conversation sessions.

    Public API (all thread-safe):
        start()                     – launch the idle-checker background thread
        stop()                      – stop idle checker, close all sessions
        get_or_create_session(...)  – get or spin up a session
        send_message(session, text) – relay a user message to the Worker
        close_session(user_id)      – close a session, run Mechanic phase
    """

    def __init__(self, config: PipelineConfig):
        self.config = config
        self._sessions: dict[str, Session] = {}  # user_id -> Session
        self._lock = threading.Lock()
        self._idle_checker: threading.Thread | None = None
        self._stop_event = threading.Event()

        # Single webhook server shared across sessions (avoids port conflicts).
        self._webhook = WebhookServer(config.webhook_host, config.webhook_port)
        self._webhook_started = False

        # Optional callback invoked after a session is closed and the
        # Mechanic phase completes.  Signature: (session, result_dict) -> None
        self.on_session_closed: Callable[[Session, dict | None], None] | None = None

    # -- lifecycle ------------------------------------------------------------

    def start(self) -> None:
        """Start the idle-timeout checker background thread."""
        if self._idle_checker is not None and self._idle_checker.is_alive():
            log.warning("Idle checker already running")
            return

        self._stop_event.clear()
        self._idle_checker = threading.Thread(
            target=self._check_idle_sessions,
            daemon=True,
            name="session-idle-checker",
        )
        self._idle_checker.start()
        log.info("Session manager started (idle timeout: %ds)", self._idle_timeout)

    def stop(self) -> None:
        """Stop the idle checker and tear down every open session."""
        self._stop_event.set()

        if self._idle_checker is not None:
            self._idle_checker.join(timeout=10)
            self._idle_checker = None

        # Snapshot user_ids under lock, then close each outside the lock
        # (close_session acquires the lock internally).
        with self._lock:
            user_ids = list(self._sessions.keys())

        for uid in user_ids:
            try:
                self.close_session(uid)
            except Exception:
                log.warning("Error closing session for %s during shutdown", uid, exc_info=True)

        log.info("Session manager stopped")

    # -- public API -----------------------------------------------------------

    def get_or_create_session(
        self,
        user_id: str,
        channel_id: str,
        first_message: str,
    ) -> tuple[Session, bool]:
        """Return an existing session or start a new one.

        *first_message* is used as the TASK_INSTRUCTION when starting a new
        container.  If the user already has an active session, the message is
        ignored here (the caller should follow up with ``send_message``).

        Returns ``(session, is_new)`` where *is_new* is True when a fresh
        container was spun up.
        """
        with self._lock:
            existing = self._sessions.get(user_id)
            if existing is not None:
                if existing.worker is not None:
                    return existing, False
                # Placeholder session still starting up — wait for it outside the lock.
                pending = existing
            else:
                pending = None

            if pending is None:
                # Reserve the slot atomically (same lock acquisition as the
                # check above) so a concurrent call for the same user_id
                # cannot also see "no session" and start a second container.
                placeholder_run_id = _generate_run_id()
                session = Session(
                    user_id=user_id,
                    channel_id=channel_id,
                    run_id=placeholder_run_id,
                    container_id="",
                    worker=None,  # type: ignore[arg-type]
                    created_at=datetime.now(timezone.utc),
                    last_activity=datetime.now(timezone.utc),
                    sandbox_version="",
                    _first_message=first_message,
                )
                self._sessions[user_id] = session

        # If another thread is already creating a session, wait for it.
        if pending is not None:
            pending._ready.wait(timeout=self._idle_timeout)
            # The creating thread may have failed and removed the session.
            # Check that the session is still registered and has a worker.
            with self._lock:
                current = self._sessions.get(user_id)
            if current is None or current.worker is None:
                raise RuntimeError(
                    f"Session creation for user {user_id} failed (waited on placeholder)"
                )
            return pending, False

        # Container startup happens outside the lock so we don't block other
        # users.  If it fails we remove the reservation.
        try:
            run_id = session.run_id
            sandbox_version = _git_short_hash(run_id)

            # Start the shared webhook server if this is the first session.
            if not self._webhook_started:
                self._webhook.start()
                self._webhook_started = True

            worker = WorkerManager(self.config, run_id, webhook=self._webhook)
            container_id = worker.start(first_message)

            # Wait for the Worker to finish processing the initial task.
            worker.wait_for_completion()

            with self._lock:
                session.container_id = container_id
                session.worker = worker
                session.sandbox_version = sandbox_version
                session.message_count = 1
                session.last_activity = datetime.now(timezone.utc)

            # Signal that the session is ready for use.
            session._ready.set()

            log.info(
                "[%s] New session for user %s (container %s, sandbox %s)",
                run_id,
                user_id,
                container_id[:12],
                sandbox_version,
            )
            return session, True

        except Exception:
            # Wake any threads waiting on this placeholder BEFORE removing
            # it, so they don't block for the full timeout duration.
            session._ready.set()
            # Roll back the reservation so the user can retry.
            with self._lock:
                self._sessions.pop(user_id, None)
            # Best-effort cleanup of partially-started worker.
            try:
                if session.worker is not None:
                    session.worker.cleanup()
            except Exception:
                pass
            raise

    def send_message(self, session: Session, text: str) -> str:
        """Send a user message to the Worker and return its response.

        Updates ``session.last_activity`` and ``session.message_count``.
        """
        if session.worker is None:
            raise RuntimeError(f"Session {session.run_id} has no active worker")

        session.worker.send_message(text)
        session.worker.wait_for_completion()
        response = session.worker.get_response()

        with self._lock:
            session.last_activity = datetime.now(timezone.utc)
            session.message_count += 1

        log.debug(
            "[%s] Message %d processed (%d chars response)",
            session.run_id,
            session.message_count,
            len(response),
        )
        return response

    def close_session(self, user_id: str) -> dict | None:
        """Close a user's session and run the Mechanic phase.

        Returns the pipeline result dict (verdict, PR URL, etc.) or None if
        the session had no meaningful changes.  Returns None silently if the
        user has no active session.
        """
        with self._lock:
            session = self._sessions.pop(user_id, None)

        if session is None:
            return None

        log.info("[%s] Closing session for user %s (%d messages)",
                 session.run_id, user_id, session.message_count)

        result: dict | None = None
        try:
            result = self._run_mechanic_phase(session)
            return result
        except Exception:
            log.error("[%s] Mechanic phase failed", session.run_id, exc_info=True)
            result = {
                "run_id": session.run_id,
                "status": "error",
                "error": "Mechanic phase failed after session close",
            }
            return result
        finally:
            self._cleanup_session(session)
            if self.on_session_closed is not None:
                try:
                    self.on_session_closed(session, result)
                except Exception:
                    log.warning(
                        "[%s] on_session_closed callback failed",
                        session.run_id,
                        exc_info=True,
                    )

    # -- background idle checker ----------------------------------------------

    def _check_idle_sessions(self) -> None:
        """Background loop: close sessions that have exceeded the idle timeout.

        Runs every ``_IDLE_CHECK_INTERVAL`` seconds until ``_stop_event`` is
        set.  Each iteration snapshots the session dict under the lock, then
        closes expired sessions outside the lock.
        """
        log.debug("Idle checker thread started")

        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=_IDLE_CHECK_INTERVAL)
            if self._stop_event.is_set():
                break

            now = datetime.now(timezone.utc)
            expired_user_ids: list[str] = []

            with self._lock:
                for uid, session in self._sessions.items():
                    idle_secs = (now - session.last_activity).total_seconds()
                    if idle_secs >= self._idle_timeout:
                        expired_user_ids.append(uid)

            for uid in expired_user_ids:
                log.info("Session for user %s idle-timed out", uid)
                try:
                    self.close_session(uid)
                except Exception:
                    log.warning("Error closing idle session for %s", uid, exc_info=True)

        log.debug("Idle checker thread exiting")

    # -- mechanic phase -------------------------------------------------------

    def _run_mechanic_phase(self, session: Session) -> dict:
        """Extract changeset, run Mechanic with feedback loop, create PR if approved.

        Reuses the same feedback-loop pattern from ``pipeline.main``.
        """
        run_id = session.run_id
        container_id = session.container_id
        task = session._first_message

        run_dir = os.path.join(self.config.output_base, run_id)
        os.makedirs(run_dir, exist_ok=True)

        summary: dict = {
            "run_id": run_id,
            "task": task,
            "status": "started",
            "iterations": 0,
            "worker_container": container_id,
            "verdict": None,
            "pr_url": None,
            "error": None,
            "session": {
                "user_id": session.user_id,
                "channel_id": session.channel_id,
                "message_count": session.message_count,
                "sandbox_version": session.sandbox_version,
                "created_at": session.created_at.isoformat(),
                "closed_at": datetime.now(timezone.utc).isoformat(),
            },
        }

        mechanic = MechanicManager(self.config, run_id)

        try:
            # ── Extract changeset ──
            extractor = ChangesetExtractor(self.config, run_id)
            changeset = extractor.extract(container_id, task=task)

            # ── No changes → skip Mechanic entirely ──
            git = changeset.get("git_changes", {})
            has_changes = (
                git.get("new_files")
                or git.get("modified_files")
                or git.get("deleted_files")
            )
            if not has_changes:
                log.info("[%s] No file changes detected — skipping Mechanic", run_id)
                summary["status"] = "no_changes"
                return summary

            # ── Mechanic feedback loop ──
            previous_rejections: list[dict] = []

            for iteration in range(1, MAX_ITERATIONS + 1):
                summary["iterations"] = iteration
                log.info("[%s] Mechanic iteration %d/%d", run_id, iteration, MAX_ITERATIONS)

                # Re-extract on subsequent iterations (Worker may have made more changes).
                if iteration > 1:
                    changeset = extractor.extract(container_id, task=task)

                changeset["previous_rejections"] = previous_rejections

                verdict = mechanic.evaluate(changeset)
                summary["verdict"] = verdict

                if verdict.get("approved"):
                    log.info("[%s] APPROVED on iteration %d", run_id, iteration)
                    pr = PRCreator(self.config, run_id)
                    pr_url = pr.create(changeset, verdict)
                    summary["pr_url"] = pr_url
                    summary["status"] = "approved"
                    break

                # ── Rejected ──
                reason = verdict.get("reason", verdict.get("rejection_reason", "No reason"))
                feedback = verdict.get("feedback", [])
                confidence = verdict.get("confidence", 0)
                log.info("[%s] REJECTED iteration %d (confidence: %s): %s",
                         run_id, iteration, confidence, reason[:200])

                previous_rejections.append({
                    "iteration": iteration,
                    "reason": reason,
                    "confidence": confidence,
                    "feedback": feedback,
                })

                disposition = verdict.get(
                    "disposition",
                    "pr" if verdict.get("approved") else None,
                )

                if disposition == "discard":
                    summary["status"] = "rejected"
                    break

                if disposition == "linear_issue":
                    summary["status"] = "linear_proposed"
                    summary["linear_proposal"] = {
                        "reason": verdict.get("disposition_reason", reason),
                        "summary": verdict.get("summary", ""),
                    }
                    break

                if iteration == MAX_ITERATIONS:
                    summary["status"] = "rejected"
                    summary["error"] = f"Failed after {MAX_ITERATIONS} mechanic iterations"
                    break

                # ── Send feedback to Worker for next iteration ──
                if not session.worker.is_alive():
                    log.error("[%s] Worker died during mechanic feedback loop", run_id)
                    summary["status"] = "error"
                    summary["error"] = "Worker container died during feedback loop"
                    break

                feedback_text = _format_feedback(feedback, reason, iteration)
                session.worker.send_feedback(feedback_text)
                session.worker.wait_for_completion()

                mechanic.cleanup()

            # Default status if loop ended without explicit assignment
            if summary["status"] == "started":
                summary["status"] = "rejected"

        except TimeoutError as exc:
            log.error("[%s] Timeout during mechanic phase: %s", run_id, exc)
            summary["status"] = "timeout"
            summary["error"] = str(exc)

        except Exception as exc:
            log.error("[%s] Mechanic phase error: %s", run_id, exc, exc_info=True)
            summary["status"] = "error"
            summary["error"] = str(exc)

        finally:
            mechanic.cleanup()

            # Persist summary to disk
            summary_path = os.path.join(run_dir, "summary.json")
            try:
                with open(summary_path, "w") as f:
                    json.dump(summary, f, indent=2, default=str)
                log.info("[%s] Session summary written to %s", run_id, summary_path)
            except Exception:
                log.warning("[%s] Could not write session summary", run_id, exc_info=True)

        return summary

    # -- helpers --------------------------------------------------------------

    @property
    def _idle_timeout(self) -> int:
        """Session idle timeout in seconds, with fallback."""
        return getattr(self.config, "session_idle_timeout", 600)

    def _cleanup_session(self, session: Session) -> None:
        """Save worker logs and remove the container."""
        if session.worker is None:
            log.debug("[%s] No worker to clean up (placeholder session)", session.run_id)
            return

        run_dir = os.path.join(self.config.output_base, session.run_id)

        # Save worker logs before killing the container.
        try:
            logs = session.worker.get_logs()
            if logs:
                os.makedirs(run_dir, exist_ok=True)
                with open(os.path.join(run_dir, "worker.log"), "w") as f:
                    f.write(logs)
        except Exception:
            log.debug("[%s] Could not save worker logs", session.run_id, exc_info=True)

        try:
            session.worker.cleanup()
        except Exception:
            log.warning("[%s] Worker cleanup failed", session.run_id, exc_info=True)

    @property
    def active_session_count(self) -> int:
        """Number of currently active sessions (for monitoring)."""
        with self._lock:
            return len(self._sessions)

    def get_session(self, user_id: str) -> Session | None:
        """Return the active session for *user_id*, or None.

        Only returns sessions where the Worker is fully initialized.
        Placeholder sessions (still starting up) return None so the
        caller doesn't try to use an uninitialized worker.
        """
        with self._lock:
            session = self._sessions.get(user_id)
            if session is not None and session.worker is None:
                return None  # still starting up
            return session
