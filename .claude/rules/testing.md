---
paths:
  - "backend/tests/**/*.py"
  - "frontend/tests/**/*.ts"
  - "frontend/e2e/**/*.ts"
---

# Test policy

Tests are permanent code. Add one only when it is the cheapest reliable way to
detect a distinct, high-impact regression. Coverage percentage, implementation
complexity, and the existence of a code path do not justify a test.

## Admission rule

A test must protect at least one of these risks:

- authentication, authorization, or another security boundary;
- data loss, corruption, cross-user leakage, or transaction atomicity;
- an external API, migration, file format, or compatibility contract;
- an edge-heavy domain algorithm whose required behavior needs examples;
- concurrency, cancellation, retry, or recovery behavior;
- browser behavior that cannot be tested more cheaply below E2E;
- recurrence of a real defect with meaningful user impact.

If two tests protect the same risk, keep the cheaper and more direct one. New
tests should replace overlapping coverage instead of adding another layer.

Do not test wiring, static rendering, CRUD happy paths, library or generated
client behavior, logs, metrics, mocks, private call sequences, internal
defaults, or exact tuning values. If a test needs more mocks than assertions,
delete it or move the assertion to a real boundary.

## Layer choice

- Unit: pure, edge-heavy computation and transformations.
- Backend integration: API, database, filesystem, transaction, and data flow.
- Frontend integration: composables, cache behavior, and component interaction.
- E2E: browser-only interaction, timing, focus, scrolling, popups, upload, and
  print integration.

After a bug fix, add a regression test only when the admission rule is met. It
must fail without the fix and live at the lowest layer that reproduces it.

Run `mise run test:backend`, `mise run test:frontend`, or `mise run test:e2e`
for the affected layer.
