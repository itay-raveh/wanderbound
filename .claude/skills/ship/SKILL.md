---
name: ship
description: Full quality pipeline — tests, simplify, code review, CLAUDE.md revision — then commit. Use instead of /commit.
user-invocable: true
allowed-tools: Bash, Read, Glob, Grep, Skill, Agent, AskUserQuestion
argument-hint: "[optional commit message hint]"
---

# Ship: Quality Pipeline + Commit

Run the full pre-commit quality pipeline, then commit. Every step must pass before proceeding.

## Step 1: Determine scope

Run `git diff --name-only HEAD` and `git diff --name-only --cached` to find all changed files.

Categorize:
- **Backend**: files in `backend/`
- **Frontend**: files in `frontend/src/` (excluding `frontend/src/client/`)
- **Config/i18n-only**: locale files, config files, documentation

## Step 2: Run scoped tests

Based on scope (use `mise run`):
- Backend changes → `mise run test:backend`
- Frontend changes → `mise run test:frontend`
- Both → both test suites
- Config/i18n-only → skip tests

**If tests fail, STOP.** Report failures. Do not continue.

## Step 3: Simplify

Use the Skill tool to invoke `simplify`. This reviews recently changed code for quality.

If it makes changes, re-run the scoped tests from Step 2.

## Step 4: Code review

Use the Skill tool to invoke `code-review:code-review`.

If critical issues are found (confidence >= 80), STOP and fix them first. Re-run tests after fixes.

## Step 5: Revise CLAUDE.md

Use the Skill tool to invoke `claude-md-management:revise-claude-md`.

## Step 6: Commit

**Important**: Before invoking the commit skill, set the pipeline marker so the pre-commit hook allows it:

```bash
touch "$CLAUDE_PROJECT_DIR/.claude/.ship-active"
```

Then use the Skill tool to invoke `commit-commands:commit`.

After the commit completes (success or failure), always clean up:

```bash
rm -f "$CLAUDE_PROJECT_DIR/.claude/.ship-active"
```

---

**If ANY step fails, stop and report. Do not skip steps.**
