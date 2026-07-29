---
name: design-audit
description: Audit and fix a frontend scope against Wanderbound's design and print constraints. Defaults to changed frontend files.
argument-hint: "[files, component, route, or area]"
user-invocable: true
allowed-tools: Agent, Skill, Bash, Read, Edit, Write, Glob, Grep
---

# Design audit

Use `$ARGUMENTS` as the scope. If it is empty, collect changed files under
`frontend/src/` and stop if there are none.

Read `frontend/DESIGN.md` and any applicable project guidance, then invoke
`impeccable:audit` for the scope. Apply confirmed findings within that scope.
Use specialized Impeccable skills only when the audit recommends them and the
work is substantial enough to benefit. Finish with the affected frontend tests
and `mise run lint:frontend`, then summarize findings, changes, and verification.
