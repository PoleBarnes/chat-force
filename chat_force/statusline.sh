#!/bin/bash
# chat-force status line for Claude Code CLI
# Receives JSON on stdin with session data
input=$(cat)

# Extract fields
CTX=$(echo "$input" | python3 -c "import sys,json; d=json.load(sys.stdin); print(int(d.get('context_window',{}).get('used_percentage',0)))" 2>/dev/null || echo "0")
DIR=$(echo "$input" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('workspace',{}).get('current_dir',''))" 2>/dev/null || echo "")

# Git branch
BRANCH=""
if [ -n "$DIR" ]; then
    BRANCH=$(git -C "$DIR" branch --show-current 2>/dev/null || echo "")
fi

# Phase from env var set by chat-force
PHASE="${CHAT_FORCE_PHASE:-build}"

# Ticket ID from .ticket-context
TICKET=""
if [ -f "$DIR/.ticket-context" ]; then
    TICKET=$(python3 -c "import json; print(json.load(open('$DIR/.ticket-context')).get('ticket_id',''))" 2>/dev/null || echo "")
fi

# Context meter color
if [ "$CTX" -ge 90 ]; then
    CTX_COLOR='\033[31m'  # red
elif [ "$CTX" -ge 70 ]; then
    CTX_COLOR='\033[33m'  # yellow
else
    CTX_COLOR='\033[32m'  # green
fi

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Phase color
case "$PHASE" in
    build)   PHASE_COLOR="$GREEN" ;;
    review)  PHASE_COLOR="$YELLOW" ;;
    improve) PHASE_COLOR="$BLUE" ;;
    *)       PHASE_COLOR="$NC" ;;
esac

# Build status line
parts="chat-force"
parts="$parts | ${PHASE_COLOR}${PHASE}${NC}"
[ -n "$BRANCH" ] && parts="$parts | $BRANCH"
[ -n "$TICKET" ] && [ "$TICKET" != "session" ] && parts="$parts | $TICKET"
parts="$parts | ${CTX_COLOR}ctx:${CTX}%${NC}"

echo -e "$parts"
