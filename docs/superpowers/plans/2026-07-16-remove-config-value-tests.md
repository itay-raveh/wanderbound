# Remove Configuration-Value Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove tests that pin internal tuning and default configuration values while preserving tests of observable behavior and external contracts.

**Architecture:** Direct configuration assertions will be deleted. Mixed tests will retain their behavioral coverage by injecting a limiter or asserting a qualitative outcome without copying internal thresholds. External API limits, protocol contracts, and configuration supplied as test input remain covered.

**Tech Stack:** pytest, Vitest, Playwright, Vue 3, AnyIO

## Global Constraints

- Use `mise run <task>` for repository tasks.
- Do not change production behavior.
- Do not retain this one-off plan in the final tree.
- Keep external service limits, HTTP contracts, and user-observable behavior covered.

---

### Task 1: Remove backend tuning assertions

**Files:**
- Modify: `backend/tests/test_media_upgrade.py`
- Modify: `backend/tests/test_dbos_runtime.py`
- Modify: `backend/tests/test_workflow_recovery.py`
- Modify: `backend/tests/test_dbos_recovery_check_script.py`

**Interfaces:**
- Consumes: existing `run_upgrade`, DBOS runtime wrappers, and workflow recovery helpers
- Produces: behavioral tests that do not assert production concurrency or timeout values

- [ ] **Step 1: Replace the upgrade concurrency tests**

Delete `test_scales_upgrade_concurrency_with_available_memory`. Patch `_upgrade_limiter` with a one-token `CapacityLimiter` in the lifecycle test, verify a second replacement does not begin while the first owns the slot, release the first, and verify both upgrades complete.

- [ ] **Step 2: Remove exact timeout assertions**

Keep assertions that DBOS teardown and workflow recovery are invoked, but stop asserting `workflow_completion_timeout_sec=5` and `timeout == 30`.

- [ ] **Step 3: Run the focused backend tests**

Run: `mise run test:backend -- tests/test_media_upgrade.py tests/test_dbos_runtime.py tests/test_workflow_recovery.py tests/test_dbos_recovery_check_script.py`

Expected: all selected tests pass.

### Task 2: Remove frontend tuning assertions

**Files:**
- Delete: `frontend/tests/composables/useUndoStack.test.ts`
- Delete: `frontend/tests/composables/useAddExternalMedia.test.ts`
- Modify: `frontend/tests/composables/useReplaceExternalMedia.test.ts`
- Modify: `frontend/tests/composables/useMediaUpgrade.test.ts`
- Modify: `frontend/tests/utils/photoQuality.test.ts`
- Modify: `frontend/e2e/active-step-sync.test.ts`

**Interfaces:**
- Consumes: existing composables and UI behavior
- Produces: tests that verify limit enforcement and scroll visibility without duplicating configured values

- [ ] **Step 1: Delete tests whose only assertion is configuration**

Delete the undo-stack capacity test, Google import picker-cap test, Google replacement picker-cap test, and exported photo-quality default test.

- [ ] **Step 2: Make frontend limit tests value-independent**

Use `GOOGLE_UPGRADE_MAX_SESSION_IDS` and `GOOGLE_UPGRADE_MAX_MATCHES` as test inputs and assert below, at, and above boundary behavior without spelling out their numeric values.

- [ ] **Step 3: Make scroll behavior qualitative**

Remove the duplicated 48 and 88 clearance constants. Assert that navigation leaves the selected page below the editor header and within the viewport.

- [ ] **Step 4: Run focused frontend tests**

Run: `mise run test:frontend -- tests/composables/useReplaceExternalMedia.test.ts tests/composables/useMediaUpgrade.test.ts tests/utils/photoQuality.test.ts`

Run: `mise run test:e2e -- e2e/active-step-sync.test.ts`

Expected: all selected tests pass.

### Task 3: Record and verify the test policy

**Files:**
- Modify: `.claude/rules/testing.md`
- Delete: `docs/superpowers/plans/2026-07-16-remove-config-value-tests.md`

**Interfaces:**
- Consumes: repository testing philosophy
- Produces: a concise rule against exact tuning-default assertions

- [ ] **Step 1: Add the policy**

State that tests must not assert exact tuning defaults such as concurrency, timeout, retry, batch-size, or cache-capacity values. Tests may inject configuration to exercise behavior and may assert external or user-visible contracts.

- [ ] **Step 2: Remove the execution plan**

Delete this file so the final tree contains no one-off planning artifact.

- [ ] **Step 3: Run full verification**

Run: `mise run test:backend`

Run: `mise run test:frontend`

Run: `mise run test:e2e`

Run: `mise run lint`

Expected: all tests and linters pass.

- [ ] **Step 4: Audit the final diff**

Search changed tests for copied tuning values and inspect `git diff --check`. Confirm every removed assertion matched the policy and no production file changed.
