#!/bin/bash
# PreToolUse hook wrapper — delegates to Python scope-card scanner.
# Blocks Edit/Write/MultiEdit on trustbit_ethanol/ if .claude/scope-card.json
# is missing/expired/invalid. Exit 0 always; the Python script emits the JSON decision.
exec python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/scope-check.py"
