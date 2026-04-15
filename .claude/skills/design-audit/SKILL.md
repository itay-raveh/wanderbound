---
name: design-audit
description: Run a comprehensive design audit, apply all fixes via sub-agents, then polish. Scope defaults to changed frontend files.
argument-hint: "[scope - files, component, or area to audit. Default: changed frontend files]"
user-invocable: true
allowed-tools: Agent, Skill, Bash, Read, Edit, Write, Glob, Grep
---

# Design Audit Workflow

You are running a structured design audit pipeline. Follow these steps exactly, as a task list.

## Step 1: Determine scope

If `$ARGUMENTS` is provided, use that as the scope.
Otherwise, find changed frontend files:
```bash
git diff --name-only HEAD; git diff --name-only --cached; git ls-files --others --exclude-standard
```
Filter to `frontend/src/**/*.{vue,ts,css,scss}` files. If no frontend files changed, tell the user and stop.

State the scope clearly before proceeding.

## Step 2: Run audit

Use the Skill tool to invoke `impeccable:audit` with the scope as the argument. Read the full audit output carefully.

## Step 3: Extract action items

From the audit output, identify:
1. Every specific issue flagged (with severity)
2. Every impeccable skill recommended (e.g., typeset, arrange, colorize, harden, etc.)
3. Any direct code fixes you can apply immediately

## Step 4: Apply direct fixes

Fix any issues that don't require a specialized skill - straightforward CSS corrections, spacing fixes, missing attributes, accessibility issues, etc. Apply these edits directly.

## Step 5: Dispatch skill sub-agents

For each recommended impeccable skill from the audit, launch a sub-agent using the Agent tool. Each sub-agent should:
- Receive the specific scope (files/components relevant to that skill's domain)
- Receive the specific issues the audit flagged for that skill
- Invoke the skill via the Skill tool (e.g., `impeccable:typeset`, `impeccable:arrange`)
- Apply all the skill's suggestions

Run independent sub-agents in parallel where possible.

## Step 6: Final polish

After all sub-agents complete, use the Skill tool to invoke `impeccable:polish` on the full scope. This is the final quality pass.

## Step 7: Summary

Report what was found, what was fixed, and what skills were invoked. Be concise.
