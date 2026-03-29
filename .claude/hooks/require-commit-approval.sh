#!/bin/bash
# Quality gate: block --no-verify (prevents bypassing git pre-commit hooks)
# and let git's own hooks enforce lint/format/type checks.
# Subjective checklist (simplify, code-review, user approval) is enforced
# by CLAUDE.md instructions, not this hook.
INPUT=$(cat)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# Only intercept git commit commands
if ! echo "$CMD" | grep -qE 'git\s+commit'; then
  exit 0
fi

# Block --no-verify flag. Only check the command line containing 'git commit',
# not the commit message body (which may mention --no-verify in text).
COMMIT_LINE=$(echo "$CMD" | grep -E 'git\s+commit')
if echo "$COMMIT_LINE" | grep -qE '\-\-no-verify'; then
  cat <<'EOF'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Do not use --no-verify. Fix the lint/format issues that git hooks are catching instead of bypassing them."}}
EOF
  exit 0
fi

# Allow — git's own pre-commit hooks handle lint, format, and type checks.
echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
exit 0
