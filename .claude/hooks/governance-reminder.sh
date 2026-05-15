#!/bin/bash
# Hook: UserPromptSubmit — inject a compact governance reminder into the main orchestrator's context.
# Runs on every user prompt. Keeps the 5-phase sequence + top rules present even when CLAUDE.md drifts.

INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.prompt // empty')

# Skip reminder for trivial prompts (short greetings, continuation tokens)
if [ ${#PROMPT} -lt 10 ]; then
    exit 0
fi

# Emit governance context. Claude receives this as additionalContext on the UserPromptSubmit event.
cat <<'EOF'
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "### Trustbit Agent Governance Reminder (auto-injected every prompt)\n\n**Delegation triggers:**\n- Feature request / \"build X\" → invoke manager FIRST\n- File edit in trustbit_ethanol/ → invoke guardian BEFORE Edit/Write\n- Bug fix → predictor → guardian → fix → code-tester → github-commit\n- Any commit → security → code-tester → github-commit (never skip)\n- Custom page / dashboard → ui-designer + planner BEFORE coding\n- \"deploy to production\" → audit → live-data-tester → security → deploy → audit\n\n**5-phase sequence (mandatory for features):**\n1. Explore (cap 5) + domain-validate business terms against code\n2. Planner → user approval → guardian\n3. Build on demo + regression BEFORE (17/17)\n4. Parallel audit: guardian, predictor, security, ui-designer, code-tester, live-data-tester — fix ALL HIGH/CRITICAL, re-invoke security after fixes\n5. Regression AFTER → user test → github-commit → deploy (on user's explicit request) → audit → memory update\n\n**Hard rules:**\n- Demo is source of truth; NEVER production without user saying \"deploy to production\"\n- locks.json is authoritative; check informal locks in memory/feature_locks.md\n- NEVER `bench clear-cache` on production (flushes sessions)\n- NEVER skip ui-designer for custom pages, NEVER skip code-tester before commit\n- Re-invoke security after fixing HIGH findings (don't commit on stale scan)\n- Git commit trailer: `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` — no \"Generated with Claude Code\"\n\nFull spec: CLAUDE.md at project root."
  }
}
EOF
exit 0
