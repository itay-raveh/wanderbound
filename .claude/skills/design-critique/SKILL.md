---
name: design-critique
description: Run a design critique, discuss questions with the user, apply suggestions via sub-agents, then run a full audit. Scope defaults to changed frontend files.
argument-hint: "[scope — files, component, or area to critique. Default: changed frontend files]"
user-invocable: true
allowed-tools: Agent, Skill, Bash, Read, Edit, Write, Glob, Grep, AskUserQuestion
---

# Design Critique Workflow

You are running a structured design critique pipeline with user involvement. Follow these steps exactly.

## Step 1: Determine scope

If `$ARGUMENTS` is provided, use that as the scope.
Otherwise, find changed frontend files:
```bash
git diff --name-only HEAD; git diff --name-only --cached; git ls-files --others --exclude-standard
```
Filter to `frontend/src/**/*.{vue,ts,css,scss}` files. If no frontend files changed, tell the user and stop.

State the scope clearly before proceeding.

## Step 2: Run critique

Use the Skill tool to invoke `impeccable:critique` with the scope as the argument. Read the full critique output carefully.

## Step 3: Develop questions

The critique will raise questions about design intent, audience, and tradeoffs. For each question or ambiguity:
1. Consider the question in context of this project (Wanderbound — a photo album generator with print-ready output, satellite maps, dark/light mode, RTL support)
2. Develop the question further — add your own observations about what you see in the code
3. Formulate clear, specific questions for the user

## Step 4: Ask the user

Use AskUserQuestion to present ALL questions to the user at once, grouped by theme. Include:
- What the critique found
- Your own observations
- The specific questions, with your recommended answer for each (so the user can just confirm or override)

Wait for the user's responses before proceeding.

## Step 5: Apply suggestions

With the user's answers as context, apply all suggestions from the critique. For each recommended impeccable skill, launch a sub-agent using the Agent tool. Each sub-agent should:
- Receive the specific scope and the user's design intent answers
- Invoke the skill via the Skill tool
- Apply all the skill's suggestions

Run independent sub-agents in parallel where possible.

## Step 6: Run full audit

Now invoke the `design-audit` skill on the same scope using the Skill tool. This runs the full audit → fix → sub-agents → polish pipeline on top of the critique work.

## Step 7: Summary

Report: what the critique found, what the user decided, what was changed, and the final audit results. Be concise.
