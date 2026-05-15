#!/bin/bash
# Temporarily unlock a locked feature for the current session.
# Usage: bash .claude/hooks/unlock.sh <FEATURE_KEY> "<reason>"
#
# Writes .claude/unlocked.json listing feature keys the lock-check hook should skip.
# Called by the orchestrator AFTER the user explicitly approves an unlock.

set -e

if [ -z "$1" ]; then
    echo "ERROR: feature key required"
    echo "Usage: unlock.sh <FEATURE_KEY> \"<reason>\""
    echo ""
    echo "Available keys (currently LOCKED):"
    python3 -c "
import json, pathlib
p = pathlib.Path('${CLAUDE_PROJECT_DIR:-.}/.claude/locks.json')
locks = json.loads(p.read_text()).get('feature_locks', {})
for k, v in locks.items():
    if v.get('status') == 'LOCKED':
        print(f'  - {k} — {v.get(\"name\", \"\")}')
"
    exit 1
fi

FEATURE_KEY="$1"
REASON="${2:-no reason given}"
UNLOCK_FILE="${CLAUDE_PROJECT_DIR:-$(pwd)}/.claude/unlocked.json"

# Verify the key exists in locks.json
python3 - "$FEATURE_KEY" <<'PY'
import json, sys, pathlib, os
key = sys.argv[1]
p = pathlib.Path(os.environ.get('CLAUDE_PROJECT_DIR', '.')) / '.claude' / 'locks.json'
locks = json.loads(p.read_text()).get('feature_locks', {})
if key not in locks:
    print(f"ERROR: unknown feature key '{key}'")
    print("Run unlock.sh with no args to list valid keys.")
    sys.exit(2)
if locks[key].get('status') != 'LOCKED':
    print(f"Note: '{key}' is not currently LOCKED (status={locks[key].get('status')})")
PY

# Load existing unlocked.json (if any) and merge
python3 - "$FEATURE_KEY" "$REASON" "$UNLOCK_FILE" <<'PY'
import json, sys, pathlib, datetime
key, reason, path = sys.argv[1], sys.argv[2], sys.argv[3]
p = pathlib.Path(path)
cfg = {"unlocked": [], "history": []}
if p.exists():
    try:
        cfg = json.loads(p.read_text())
    except Exception:
        pass
unlocked = set(cfg.get("unlocked", []))
unlocked.add(key)
cfg["unlocked"] = sorted(unlocked)
cfg.setdefault("history", []).append({
    "action": "unlock",
    "key": key,
    "reason": reason,
    "at": datetime.datetime.now().isoformat(timespec="seconds"),
})
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(cfg, indent=2))
print(f"✓ Unlocked: {key}")
print(f"  Reason: {reason}")
print(f"  Active unlocks: {', '.join(cfg['unlocked'])}")
print(f"  File: {p}")
print()
print("NEXT STEPS:")
print("  1. Run regression BEFORE: test_regression.py on demo (17/17 required)")
print("  2. Make the change on demo only")
print("  3. Run regression AFTER: must still be 17/17")
print("  4. User tests on demo")
print("  5. Re-lock: bash .claude/hooks/relock.sh " + key)
PY
