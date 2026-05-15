#!/usr/bin/env python3
"""
Guardian Lock Check — PreToolUse hook for Edit/Write/MultiEdit.

Reads tool input from stdin (Claude Code hook protocol), extracts the target
file path, scans locks.json for matches against:
  - protected_files (exact path OR filename match anywhere in protected_files list)
  - protected_code (grep for function name inside new_string)
  - protected_fields (grep for fieldname inside new_string)
  - protected_settings (grep for setting key inside new_string)

If a match is found AND the feature key is NOT in .claude/unlocked.json,
emits a DENY decision with a detailed block message.

Unlock procedure:
  echo '{"unlocked": ["FEATURE_KEY"], "reason": "...", "until": "YYYY-MM-DD"}' \\
    > .claude/unlocked.json
  (or use .claude/hooks/unlock.sh FEATURE_KEY "reason")

Exit codes:
  0 — emitted decision (may be deny or allow)
  1 — scanner error (fail-closed, no decision emitted → Claude Code treats as allow)
"""

import json
import os
import re
import sys
from pathlib import Path


def load_json(path):
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except Exception:
        return {}


def project_dir():
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()


def normalize(p):
    """Normalize a path for matching — lowercase, forward slashes."""
    return str(p).replace("\\", "/").lower()


def extract_filename(protected_entry):
    """
    protected_files entries may be strings like:
      "ts_po_approval.py (MR sections: _submit_mr_for_approval, ...)"
    Extract the filename portion only.
    """
    # Take the first whitespace-delimited token, stripping punctuation
    token = protected_entry.strip().split()[0] if protected_entry.strip() else ""
    return normalize(token.rstrip(":").rstrip(","))


def file_matches_locked(file_path, lock):
    """Return True if file_path matches any protected_files entry of this lock."""
    if not file_path:
        return False
    fp = normalize(file_path)
    for entry in lock.get("protected_files", []) + lock.get("protected_items", []):
        if not isinstance(entry, str):
            continue
        name = extract_filename(entry)
        if not name:
            continue
        # Exact filename match OR path contains the protected name as a segment
        if fp.endswith("/" + name) or fp.endswith(name) or name in fp.split("/"):
            return True
    return False


def content_touches_protected_code(content, lock):
    """
    For Write/Edit new_string content, check if any protected_code identifier
    (function name, line hint, button class) appears.
    """
    if not content:
        return []
    hits = []
    for entry in lock.get("protected_code", []):
        if not isinstance(entry, str):
            continue
        # Extract likely function names: _snake_case identifiers and Capitalized words
        for ident in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", entry):
            # Skip very generic words
            if ident in ("the", "and", "for", "file", "line", "with", "check", "must",
                         "buttons", "stepper", "banners", "entire", "sections",
                         "status", "True", "False", "None", "HIGH", "LOW", "CRITICAL"):
                continue
            if ident in content and len(ident) >= 4:
                hits.append((entry, ident))
                break  # one hit per entry is enough
    return hits


def content_touches_protected_fields(content, lock):
    if not content:
        return []
    hits = []
    for entry in lock.get("protected_fields", []):
        if not isinstance(entry, str):
            continue
        fieldname = entry.split()[0] if entry.strip() else ""
        fieldname = fieldname.strip(",:")
        if fieldname and len(fieldname) >= 3 and fieldname in content:
            hits.append(fieldname)
    return hits


def content_touches_protected_settings(content, lock):
    if not content:
        return []
    hits = []
    for entry in lock.get("protected_settings", []):
        if not isinstance(entry, str):
            continue
        # Extract the setting key (e.g., "restart_supervisor_on_update" from the line)
        m = re.search(r"(\w+)\s*=", entry) or re.search(r"(\w+)\s*:", entry)
        key = m.group(1) if m else entry.split(":")[-1].split("=")[0].strip().split()[0]
        if key and len(key) >= 4 and key in content:
            hits.append(key)
    return hits


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception as e:
        # Fail-closed but silent: let the tool through if we can't parse
        print(f"[lock-check] parse error: {e}", file=sys.stderr)
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    # Only intercept file-mutation tools
    if tool_name not in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        sys.exit(0)

    file_path = tool_input.get("file_path", "") or tool_input.get("notebook_path", "")
    # Collect any content that will be written (for in-content identifier scan)
    content_parts = []
    if tool_name == "Write":
        content_parts.append(tool_input.get("content", "") or "")
    elif tool_name == "Edit":
        content_parts.append(tool_input.get("new_string", "") or "")
        content_parts.append(tool_input.get("old_string", "") or "")
    elif tool_name == "MultiEdit":
        for edit in tool_input.get("edits", []) or []:
            content_parts.append(edit.get("new_string", "") or "")
            content_parts.append(edit.get("old_string", "") or "")
    content = "\n".join(content_parts)

    pdir = project_dir()
    locks = load_json(pdir / ".claude" / "locks.json").get("feature_locks", {})
    unlocked_cfg = load_json(pdir / ".claude" / "unlocked.json")
    unlocked = set(unlocked_cfg.get("unlocked", []))

    # Only guard files under the app root
    if "trustbit_ethanol" not in normalize(file_path):
        sys.exit(0)

    matches = []  # list of (feature_key, feature_name, reason, details)
    for key, lock in locks.items():
        if key in unlocked:
            continue
        if lock.get("status") != "LOCKED":
            continue

        file_hit = file_matches_locked(file_path, lock)
        code_hits = content_touches_protected_code(content, lock) if file_hit else []
        field_hits = content_touches_protected_fields(content, lock) if file_hit else []
        setting_hits = content_touches_protected_settings(content, lock) if file_hit else []

        # Heuristic: flag on file match alone (conservative — any edit to a locked file)
        if file_hit:
            matches.append({
                "key": key,
                "name": lock.get("name", key),
                "locked_on": lock.get("locked_on", "?"),
                "reason": lock.get("reason", ""),
                "file_match": True,
                "code_hits": [c[1] for c in code_hits],
                "field_hits": field_hits,
                "setting_hits": setting_hits,
                "if_changing": lock.get("if_changing", "Run regression before + after, re-lock after")
            })

    if not matches:
        # No lock hit — allow silently
        sys.exit(0)

    # Build BLOCK message
    msg_lines = [
        "⛔ GUARDIAN BLOCK — {} locked feature(s) would be affected:".format(len(matches)),
        "",
    ]
    for i, m in enumerate(matches, 1):
        msg_lines.append(f"{i}. [{m['key']}] {m['name']}")
        msg_lines.append(f"   Locked: {m['locked_on']}")
        msg_lines.append(f"   Reason: {m['reason']}")
        extras = []
        if m["code_hits"]:
            extras.append("functions/identifiers touched: " + ", ".join(m["code_hits"][:5]))
        if m["field_hits"]:
            extras.append("fields touched: " + ", ".join(m["field_hits"][:5]))
        if m["setting_hits"]:
            extras.append("settings touched: " + ", ".join(m["setting_hits"][:5]))
        for e in extras:
            msg_lines.append(f"   ⚠  {e}")
        msg_lines.append(f"   Before changing: {m['if_changing']}")
        msg_lines.append("")

    msg_lines.extend([
        "UNLOCK PROCEDURE:",
        "  1. Ask user for explicit approval: \"This change touches locked feature X. Unlock?\"",
        "  2. Run regression BEFORE: test_regression.py on demo → must be 17/17",
        "  3. Unlock this session: bash .claude/hooks/unlock.sh <FEATURE_KEY> \"<reason>\"",
        "  4. Make the change",
        "  5. Run regression AFTER → must be 17/17",
        "  6. Re-lock: bash .claude/hooks/relock.sh <FEATURE_KEY>",
        "",
        "To override this block for the current edit ONLY, the user must say \"unlock <FEATURE_KEY>\"",
        "and the orchestrator must run the unlock script before retrying.",
    ])
    block_message = "\n".join(msg_lines)

    # Claude Code hook protocol: PreToolUse deny
    decision = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": block_message,
        }
    }
    print(json.dumps(decision))
    sys.exit(0)


if __name__ == "__main__":
    main()
