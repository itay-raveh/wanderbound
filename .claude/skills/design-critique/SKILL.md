---
name: design-critique
description: Critique a frontend scope, resolve design decisions with the user, then apply approved changes. Defaults to changed frontend files.
argument-hint: "[files, component, route, or area]"
user-invocable: true
allowed-tools: Agent, Skill, Bash, Read, Edit, Write, Glob, Grep, AskUserQuestion
---

# Design critique

Use `$ARGUMENTS` as the scope. If it is empty, collect changed files under
`frontend/src/` and stop if there are none.

Read `frontend/DESIGN.md` and invoke `impeccable:critique` for the scope. Present
the critique's real design decisions together, with a recommendation for each,
and wait for the user. Apply only the approved direction. Use specialized
Impeccable skills when their focused workflow adds value, then run
`impeccable:audit`, the affected frontend tests, and `mise run lint:frontend`.
Summarize the decisions, changes, and verification.
