#!/bin/bash
# Hook: Block direct SSH commands to production server unless user explicitly approved
INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Check if command targets production server
if echo "$COMMAND" | grep -q "<ETHANOL_PROD_IP>"; then
    # Check if command is a deploy (git pull, bench build, bench migrate)
    if echo "$COMMAND" | grep -qE "git pull|bench build|bench migrate|supervisorctl|bench restart|bench clear-cache"; then
        echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"WARNING: This command targets the PRODUCTION server (<ETHANOL_PROD_IP>). Only proceed if the user explicitly asked to deploy to production."}}'
        exit 0
    fi
fi

exit 0
