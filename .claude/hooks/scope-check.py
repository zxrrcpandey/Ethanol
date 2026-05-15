#!/usr/bin/env python3
"""
Scope-Card Check — PreToolUse hook for Edit/Write/MultiEdit on trustbit_ethanol/.

Forces a per-task scope declaration BEFORE any code change, to prevent the
chronic over-engineering pattern documented in:
  memory/feedback_over_engineering_audit.md
  memory/feedback_production_parity.md  (Lesson 210)

Reads tool input from stdin (Claude Code hook protocol). If the target file is
under trustbit_ethanol/, requires .claude/scope-card.json to:
  - exist
  - have non-empty user_quote, interpretation, justification
  - have a valid track in {lightweight, full, disaster}
  - have expires_at in the future (default scope-card lifetime: 60 minutes)
  - declare loc_target (int), files_target (int), skip_agents (list)

If any check fails → emit DENY with helpful message + how to create the scope-card.

How to create / refresh the scope-card:
  bash .claude/hooks/scope-card-write.sh <track>     (helper)
  OR write .claude/scope-card.json directly with all required fields.

Tracks:
  lightweight  — ≤50 LOC OR ≤3 files. Skip planner / ui-designer / code-tester.
                 Keep guardian + security + regression-17.
  full         — >50 LOC OR >3 files OR explicit feature. Full 5-phase pipeline.
  disaster     — >500 LOC. User MUST explicitly approve "yes, full feature".

Exit codes:
  0 — emitted decision (allow or deny)
  1 — scanner error (fail-closed: no decision → treated as allow by Claude Code)
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


# Tracks allowed
VALID_TRACKS = {"lightweight", "full", "disaster"}

# Path-prefix that triggers the scope-card requirement
TRIGGER_PREFIX = "trustbit_ethanol/"

# Required fields on scope-card.json
REQUIRED_FIELDS = (
    "user_quote",
    "interpretation",
    "loc_target",
    "files_target",
    "track",
    "skip_agents",
    "expires_at",
    "justification",
)


def emit(decision: str, reason: str):
    """Emit a Claude Code hook decision and exit cleanly."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,  # "allow" | "deny" | "ask"
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(payload))
    sys.exit(0)


def project_dir() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()


def file_path_from_input(payload: dict) -> str:
    """Extract the target file_path from Edit/Write/MultiEdit/NotebookEdit input."""
    tool_input = payload.get("tool_input", {}) or {}
    return tool_input.get("file_path") or tool_input.get("notebook_path") or ""


def is_in_trigger_zone(file_path: str) -> bool:
    """Return True if file_path is inside trustbit_ethanol/."""
    return TRIGGER_PREFIX in file_path.replace("\\", "/")


def parse_iso(s: str) -> datetime:
    """Parse ISO datetime; tolerate trailing Z."""
    if not isinstance(s, str):
        raise ValueError("expires_at must be an ISO datetime string")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def scope_card_violations(card: dict) -> list:
    """Return a list of human-readable violations of the scope-card. Empty = valid."""
    errors = []
    for f in REQUIRED_FIELDS:
        if f not in card:
            errors.append(f"missing required field: '{f}'")
    if errors:
        return errors  # bail early if structure is wrong

    # Field-by-field validation
    if not isinstance(card["user_quote"], str) or not card["user_quote"].strip():
        errors.append("'user_quote' must be a non-empty string (verbatim user words)")
    if not isinstance(card["interpretation"], str) or not card["interpretation"].strip():
        errors.append("'interpretation' must be a non-empty 1-sentence summary")
    if not isinstance(card["justification"], str) or not card["justification"].strip():
        errors.append("'justification' must be a non-empty 1-sentence rationale")

    if not isinstance(card["loc_target"], int) or card["loc_target"] < 0:
        errors.append("'loc_target' must be a non-negative integer")
    if not isinstance(card["files_target"], int) or card["files_target"] < 0:
        errors.append("'files_target' must be a non-negative integer")

    track = card.get("track")
    if track not in VALID_TRACKS:
        errors.append(f"'track' must be one of {sorted(VALID_TRACKS)}")

    if not isinstance(card["skip_agents"], list):
        errors.append("'skip_agents' must be a list")

    # Expiry check
    try:
        exp = parse_iso(card["expires_at"])
        now = datetime.now(timezone.utc)
        # Tolerate naive datetimes (assume UTC)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < now:
            errors.append(
                f"scope-card expired at {card['expires_at']} (now {now.isoformat()}). "
                "Refresh it before continuing."
            )
    except Exception as e:
        errors.append(f"'expires_at' invalid: {e}")

    # Track / size sanity check (informational — don't block, but flag)
    loc = card.get("loc_target", 0)
    files = card.get("files_target", 0)
    if track == "lightweight" and (loc > 50 or files > 3):
        errors.append(
            f"track='lightweight' but loc_target={loc} files_target={files} "
            f"exceeds lightweight bounds (≤50 LOC AND ≤3 files). "
            "Either tighten scope or upgrade track to 'full'."
        )
    if track == "full" and loc > 500:
        errors.append(
            f"track='full' but loc_target={loc} exceeds 500 LOC. "
            "Use track='disaster' which requires explicit user approval."
        )

    return errors


def deny_message(card_path: Path, violations: list) -> str:
    """Build the denial message for Claude Code."""
    if violations and any("missing required field" in v or "expired" in v.lower() or "invalid" in v.lower() for v in violations) and not card_path.exists():
        # Card doesn't exist case
        return (
            "BLOCKED: scope-card missing.\n\n"
            "Before editing any file under trustbit_ethanol/, you must declare "
            "scope by writing .claude/scope-card.json (lifetime: 60 minutes). "
            "This prevents chronic over-engineering — see "
            "memory/feedback_over_engineering_audit.md.\n\n"
            "Required JSON shape:\n"
            "{\n"
            '  "user_quote": "<verbatim user words>",\n'
            '  "interpretation": "<1-sentence what user wants>",\n'
            '  "loc_target": <int>,\n'
            '  "files_target": <int>,\n'
            '  "track": "lightweight" | "full" | "disaster",\n'
            '  "skip_agents": ["planner", "ui-designer", ...],\n'
            '  "expires_at": "<ISO 8601 datetime, +60min from now>",\n'
            '  "justification": "<1-sentence why this size is right>"\n'
            "}\n\n"
            "Tracks:\n"
            "  lightweight  ≤50 LOC AND ≤3 files. Skip planner/ui-designer/code-tester. Keep guardian+security+regression.\n"
            "  full         >50 LOC OR >3 files OR explicit feature. Full 5-phase pipeline.\n"
            "  disaster     >500 LOC. User must explicitly approve \"yes, full feature\".\n\n"
            "After writing scope-card.json, retry the Edit/Write."
        )

    bullet_list = "\n".join(f"  - {v}" for v in violations)
    return (
        f"BLOCKED: scope-card has {len(violations)} violation(s):\n"
        f"{bullet_list}\n\n"
        f"Fix the issues in {card_path.relative_to(project_dir())} and retry. "
        f"See memory/feedback_over_engineering_audit.md for the full mechanism rationale."
    )


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        # Fail-open on malformed input (matches lock-check.py pattern)
        sys.exit(1)

    file_path = file_path_from_input(payload)
    if not file_path or not is_in_trigger_zone(file_path):
        # Out of scope — allow without comment
        sys.exit(0)

    pdir = project_dir()
    card_path = pdir / ".claude" / "scope-card.json"

    if not card_path.exists():
        emit("deny", deny_message(card_path, ["missing required field: scope-card file does not exist"]))

    try:
        card = json.loads(card_path.read_text())
    except Exception as e:
        emit("deny", f"BLOCKED: scope-card.json is unreadable ({e}). Rewrite it.")

    violations = scope_card_violations(card)
    if violations:
        emit("deny", deny_message(card_path, violations))

    # Card valid — allow.
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Fail-closed: emit error to stderr but don't crash the hook chain
        sys.stderr.write(f"scope-check.py error: {e}\n")
        sys.exit(1)
