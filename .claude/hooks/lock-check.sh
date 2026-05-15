#!/bin/bash
# PreToolUse hook wrapper — delegates to Python scanner.
# Exit 0 always; the Python script emits the JSON decision.
exec python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/lock-check.py"
