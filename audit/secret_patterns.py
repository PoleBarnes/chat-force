"""Secret detection patterns.

Used by:
- Audit logger: scrub secrets from log entries
- Git pre-push hook: scan for accidentally committed secrets
- Runtime secret injection validation

Each pattern is a tuple of (regex, name, severity) where severity is one of:
- critical: immediate block, must never appear in logs or commits
- high: strong indicator of a secret, should be blocked
- medium: possible false positive, flag for review
"""

from __future__ import annotations

import re

SECRET_PATTERNS: list[tuple[str, str, str]] = [
    # --- Anthropic ---
    (r'sk-ant-[a-zA-Z0-9_-]{20,}', 'Anthropic API Key', 'critical'),

    # --- Slack ---
    (r'xoxb-[0-9]+-[0-9]+-[a-zA-Z0-9]+', 'Slack Bot Token', 'critical'),
    (r'xoxp-[0-9]+-[0-9]+-[0-9]+-[a-f0-9]+', 'Slack User Token', 'critical'),
    (r'xapp-[0-9]+-[A-Za-z0-9]+-[0-9]+-[a-f0-9]+', 'Slack App Token', 'critical'),
    (r'xoxo-[0-9]+-[0-9]+-[a-zA-Z0-9]+', 'Slack Legacy Token', 'critical'),

    # --- GitHub ---
    (r'ghp_[a-zA-Z0-9]{36}', 'GitHub Personal Access Token', 'critical'),
    (r'gho_[a-zA-Z0-9]{36}', 'GitHub OAuth Token', 'critical'),
    (r'ghs_[a-zA-Z0-9]{36}', 'GitHub Server Token', 'critical'),
    (r'ghr_[a-zA-Z0-9]{36}', 'GitHub Refresh Token', 'critical'),
    (r'github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59}', 'GitHub Fine-Grained PAT', 'critical'),

    # --- Google ---
    (r'AIza[0-9A-Za-z_-]{35}', 'Google API Key', 'high'),

    # --- Doppler ---
    (r'dp\.st\.[a-zA-Z0-9_-]+', 'Doppler Service Token', 'critical'),
    (r'dp\.ct\.[a-zA-Z0-9_-]+', 'Doppler CLI Token', 'critical'),

    # --- AWS ---
    (r'AKIA[0-9A-Z]{16}', 'AWS Access Key ID', 'critical'),
    (r'(?:aws_secret_access_key|AWS_SECRET_ACCESS_KEY)\s*[:=]\s*["\']?[A-Za-z0-9/+=]{40}', 'AWS Secret Access Key', 'critical'),

    # --- OpenAI ---
    (r'sk-[a-zA-Z0-9]{20,}', 'OpenAI API Key', 'critical'),

    # --- Stripe ---
    (r'sk_live_[a-zA-Z0-9]{24,}', 'Stripe Live Secret Key', 'critical'),
    (r'rk_live_[a-zA-Z0-9]{24,}', 'Stripe Live Restricted Key', 'critical'),

    # --- Twilio ---
    (r'SK[a-f0-9]{32}', 'Twilio API Key', 'high'),

    # --- SendGrid ---
    (r'SG\.[a-zA-Z0-9_-]{22}\.[a-zA-Z0-9_-]{43}', 'SendGrid API Key', 'critical'),

    # --- Generic secrets ---
    (r'-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----', 'Private Key', 'critical'),
    (r'-----BEGIN CERTIFICATE-----', 'Certificate (review if private)', 'medium'),
    (r'password\s*[:=]\s*["\'][^"\']{8,}["\']', 'Hardcoded Password', 'high'),
    (r'secret\s*[:=]\s*["\'][^"\']{8,}["\']', 'Hardcoded Secret', 'high'),
    (r'api[_-]?key\s*[:=]\s*["\'][^"\']{8,}["\']', 'Hardcoded API Key', 'high'),
    (r'token\s*[:=]\s*["\'][^"\']{8,}["\']', 'Hardcoded Token', 'medium'),
    (r'bearer\s+[a-zA-Z0-9_\-.~+/]+=*', 'Bearer Token in Header', 'high'),
]

# Pre-compiled patterns for performance
COMPILED_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (re.compile(pattern, re.IGNORECASE if severity == 'medium' else 0), name, severity)
    for pattern, name, severity in SECRET_PATTERNS
]


def scan_text(text: str) -> list[dict]:
    """Scan text for secret patterns.

    Returns a list of findings, each with:
    - pattern_name: human-readable name of the matched pattern
    - severity: critical, high, or medium
    - match: the matched text (first 8 chars + '...' for safety)
    - position: character offset in the text
    """
    findings = []
    for compiled_re, name, severity in COMPILED_PATTERNS:
        for match in compiled_re.finditer(text):
            matched_text = match.group()
            # Truncate the matched value so we don't log the full secret
            safe_preview = matched_text[:8] + '...' if len(matched_text) > 8 else matched_text
            findings.append({
                'pattern_name': name,
                'severity': severity,
                'match_preview': safe_preview,
                'position': match.start(),
            })
    return findings


def has_secrets(text: str, min_severity: str = 'medium') -> bool:
    """Quick check: does this text contain any secrets at or above the given severity?

    Severity ordering: critical > high > medium
    """
    severity_rank = {'medium': 0, 'high': 1, 'critical': 2}
    min_rank = severity_rank.get(min_severity, 0)

    for compiled_re, _name, severity in COMPILED_PATTERNS:
        if severity_rank.get(severity, 0) >= min_rank:
            if compiled_re.search(text):
                return True
    return False


def scrub_text(text: str, replacement: str = '[REDACTED]') -> str:
    """Replace all detected secrets in text with a redaction marker."""
    result = text
    for compiled_re, _name, _severity in COMPILED_PATTERNS:
        result = compiled_re.sub(replacement, result)
    return result
