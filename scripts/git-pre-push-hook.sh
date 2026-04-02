#!/usr/bin/env bash
# =============================================================================
# Git pre-push hook — scans pushed commits for secrets
#
# Install:
#   cp scripts/git-pre-push-hook.sh .git/hooks/pre-push && chmod +x .git/hooks/pre-push
#
# Bypass (emergency only):
#   git push --no-verify
#   WARNING: bypassing secret scanning is logged and should only be used
#   in genuine emergencies. You are responsible for manual review.
# =============================================================================

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
PATTERNS_PY="$REPO_ROOT/audit/secret_patterns.py"

# ANSI colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ---------------------------------------------------------------------------
# Secret patterns (fallback if Python is unavailable)
# Keep in sync with audit/secret_patterns.py
# ---------------------------------------------------------------------------
FALLBACK_PATTERNS=(
    'sk-ant-[a-zA-Z0-9_-]{20,}'
    'xoxb-[0-9]+-[0-9]+-[a-zA-Z0-9]+'
    'xoxp-[0-9]+-[0-9]+-[0-9]+-[a-f0-9]+'
    'xapp-[0-9]+-[A-Za-z0-9]+-[0-9]+-[a-f0-9]+'
    'ghp_[a-zA-Z0-9]{36}'
    'gho_[a-zA-Z0-9]{36}'
    'ghs_[a-zA-Z0-9]{36}'
    'ghr_[a-zA-Z0-9]{36}'
    'github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59}'
    'AIza[0-9A-Za-z_-]{35}'
    'dp\.st\.[a-zA-Z0-9_-]+'
    'dp\.ct\.[a-zA-Z0-9_-]+'
    'AKIA[0-9A-Z]{16}'
    'sk-[a-zA-Z0-9]{20,}'
    'sk_live_[a-zA-Z0-9]{24,}'
    'SG\.[a-zA-Z0-9_-]{22}\.[a-zA-Z0-9_-]{43}'
    '-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'
)

# ---------------------------------------------------------------------------
# Scan using Python (preferred — uses canonical patterns)
# ---------------------------------------------------------------------------
scan_with_python() {
    local diff_content="$1"
    python3 -c "
import sys, os
sys.path.insert(0, '$REPO_ROOT')
from audit.secret_patterns import scan_text

text = sys.stdin.read()
findings = scan_text(text)
if findings:
    for f in findings:
        sev = f['severity'].upper()
        name = f['pattern_name']
        preview = f['match_preview']
        print(f'  [{sev}] {name}: {preview}')
    sys.exit(1)
sys.exit(0)
" <<< "$diff_content"
}

# ---------------------------------------------------------------------------
# Scan using grep (fallback)
# ---------------------------------------------------------------------------
scan_with_grep() {
    local diff_content="$1"
    local found=0

    for pattern in "${FALLBACK_PATTERNS[@]}"; do
        matches=$(echo "$diff_content" | grep -En "$pattern" 2>/dev/null || true)
        if [ -n "$matches" ]; then
            echo -e "  ${RED}Pattern match:${NC} $pattern"
            echo "$matches" | head -5 | while IFS= read -r line; do
                echo "    $line"
            done
            found=1
        fi
    done

    return $found
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

echo "=== Pre-push secret scan ==="

# Read the push info from stdin (provided by git)
# Format: <local ref> <local sha> <remote ref> <remote sha>
SECRETS_FOUND=0

while read -r local_ref local_sha remote_ref remote_sha; do
    # Skip delete pushes
    if [ "$local_sha" = "0000000000000000000000000000000000000000" ]; then
        continue
    fi

    # Determine the range of commits to scan
    if [ "$remote_sha" = "0000000000000000000000000000000000000000" ]; then
        # New branch — scan all commits not on any remote branch
        range="$local_sha --not --remotes"
    else
        range="$remote_sha..$local_sha"
    fi

    # Get the diff content for all commits in the range
    diff_content=$(git diff "$remote_sha" "$local_sha" -- 2>/dev/null || git show --format="" "$local_sha" 2>/dev/null || echo "")

    if [ -z "$diff_content" ]; then
        continue
    fi

    echo "Scanning $(echo "$range" | head -c 40)..."

    # Try Python scanner first, fall back to grep
    if command -v python3 &>/dev/null && [ -f "$PATTERNS_PY" ]; then
        if ! scan_with_python "$diff_content"; then
            SECRETS_FOUND=1
        fi
    else
        if ! scan_with_grep "$diff_content"; then
            SECRETS_FOUND=1
        fi
    fi
done

if [ "$SECRETS_FOUND" -eq 1 ]; then
    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED} PUSH BLOCKED: Potential secrets found  ${NC}"
    echo -e "${RED}========================================${NC}"
    echo ""
    echo "Review the findings above and remove any secrets before pushing."
    echo "Secrets should be managed via Doppler, not committed to the repo."
    echo ""
    echo -e "${YELLOW}Emergency bypass (use with extreme caution):${NC}"
    echo "  git push --no-verify"
    echo ""
    echo -e "${YELLOW}WARNING: Bypassing secret scanning is your responsibility.${NC}"
    echo "         Ensure no real secrets are in the pushed commits."
    exit 1
fi

echo "No secrets detected. Push proceeding."
exit 0
