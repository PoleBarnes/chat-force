"""Audit subsystem for the Digital Workforce Platform."""

from .audit_logger import AuditLogger, AuditEventType
from .secret_patterns import scan_text, has_secrets, scrub_text

__all__ = [
    "AuditLogger",
    "AuditEventType",
    "scan_text",
    "has_secrets",
    "scrub_text",
]
