#!/bin/bash
# Helper: write .claude/scope-card.json with sensible defaults.
# Usage: scope-card-write.sh <track> [loc_target] [files_target]
# Example: scope-card-write.sh lightweight 30 2

set -e
TRACK="${1:-}"
LOC="${2:-}"
FILES="${3:-}"
DIR="${CLAUDE_PROJECT_DIR:-.}"
OUT="$DIR/.claude/scope-card.json"

if [[ -z "$TRACK" ]]; then
  echo "Usage: $0 <track:lightweight|full|disaster> [loc_target] [files_target]"
  echo "  lightweight: ≤50 LOC AND ≤3 files"
  echo "  full       : >50 LOC OR >3 files OR explicit feature"
  echo "  disaster   : >500 LOC (requires explicit user approval)"
  exit 1
fi

# Defaults per track
case "$TRACK" in
  lightweight) LOC="${LOC:-50}";  FILES="${FILES:-3}" ;;
  full)        LOC="${LOC:-200}"; FILES="${FILES:-8}" ;;
  disaster)    LOC="${LOC:-1000}"; FILES="${FILES:-15}" ;;
  *) echo "Invalid track: $TRACK"; exit 1 ;;
esac

# Skip-agent suggestions per track
case "$TRACK" in
  lightweight) SKIP='["planner","ui-designer","code-tester","live-data-tester"]' ;;
  full)        SKIP='[]' ;;
  disaster)    SKIP='[]' ;;
esac

EXPIRES=$(python3 -c "from datetime import datetime, timedelta, timezone; print((datetime.now(timezone.utc)+timedelta(minutes=60)).isoformat())")

cat > "$OUT" <<EOF
{
  "user_quote": "<TODO: paste verbatim user words here>",
  "interpretation": "<TODO: 1-sentence what user wants>",
  "loc_target": $LOC,
  "files_target": $FILES,
  "track": "$TRACK",
  "skip_agents": $SKIP,
  "expires_at": "$EXPIRES",
  "justification": "<TODO: 1-sentence why this size is right>"
}
EOF

echo "Wrote $OUT (track=$TRACK, loc=$LOC, files=$FILES, expires=$EXPIRES)"
echo "EDIT the file to fill user_quote, interpretation, justification fields."
