#!/bin/bash
# Quality gate: enforce /ship pipeline for all commits.
# Blocks raw git commit unless the /ship skill set the marker file.
# Also blocks --no-verify (no bypassing pre-commit hooks).
INPUT=$(cat)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# Only intercept git commit commands
if ! echo "$CMD" | grep -qE 'git\s+commit'; then
  exit 0
fi

# Block --no-verify flag
COMMIT_LINE=$(echo "$CMD" | grep -E 'git\s+commit')
if echo "$COMMIT_LINE" | grep -qE '\-\-no-verify'; then
  jq -n '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: "Do not use --no-verify. Fix the lint/format issues instead."
    }
  }'
  exit 0
fi

# Check if /ship pipeline is active (marker file)
MARKER="$CLAUDE_PROJECT_DIR/.claude/.ship-active"
if [ -f "$MARKER" ]; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
  exit 0
fi

# Block: not running through /ship
jq -n '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: "Use /ship instead of raw git commit. /ship runs the full quality pipeline (tests, /simplify, /code-review, /revise-claude-md) before committing."
  }
}'
exit 0
