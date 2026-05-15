#!/bin/bash
# Re-lock a feature after changes are complete and tested.
# Usage: bash .claude/hooks/relock.sh <FEATURE_KEY> ["<reason for re-lock>"]
#
# Removes the key from .claude/unlocked.json and updates lock_history in locks.json.

set -e

if [ -z "$1" ]; then
    echo "ERROR: feature key required"
    echo "Usage: relock.sh <FEATURE_KEY> [\"<reason>\"]"
    exit 1
fi

FEATURE_KEY="$1"
REASON="${2:-Re-locked after successful change and regression PASS}"
UNLOCK_FILE="${CLAUDE_PROJECT_DIR:-$(pwd)}/.claude/unlocked.json"
LOCKS_FILE="${CLAUDE_PROJECT_DIR:-$(pwd)}/.claude/locks.json"

python3 - "$FEATURE_KEY" "$REASON" "$UNLOCK_FILE" "$LOCKS_FILE" <<'PY'
import json, sys, pathlib, datetime
key, reason, ufile, lfile = sys.argv[1:5]

# 1. Remove from unlocked.json
up = pathlib.Path(ufile)
if up.exists():
    cfg = json.loads(up.read_text())
    unlocked = set(cfg.get("unlocked", []))
    if key in unlocked:
        unlocked.discard(key)
        cfg["unlocked"] = sorted(unlocked)
        cfg.setdefault("history", []).append({
            "action": "relock",
            "key": key,
            "reason": reason,
            "at": datetime.datetime.now().isoformat(timespec="seconds"),
        })
        up.write_text(json.dumps(cfg, indent=2))
        print(f"✓ Removed {key} from session unlocks")
    else:
        print(f"Note: {key} was not in session unlocks")
else:
    print("Note: no unlocked.json — nothing to remove from session")

# 2. Update lock_history + locked_on in locks.json
lp = pathlib.Path(lfile)
locks = json.loads(lp.read_text())
today = datetime.date.today().isoformat()
if key in locks.get("feature_locks", {}):
    locks["feature_locks"][key]["status"] = "LOCKED"
    locks["feature_locks"][key]["locked_on"] = today
    locks.setdefault("lock_history", []).append({
        "action": "RE_LOCK",
        "key": key,
        "reason": reason,
        "date": today,
    })
    lp.write_text(json.dumps(locks, indent=2))
    print(f"✓ {key} status=LOCKED, locked_on={today}")
    print(f"  Reason logged: {reason}")
else:
    print(f"WARNING: {key} not found in locks.json — lock_history updated but no feature state changed")
PY
