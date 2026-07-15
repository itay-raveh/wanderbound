# Chapter Navigation Instant Jump Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent chapter cover navigation from entering smooth virtualizer reconciliation when its target measurement is temporarily unavailable.

**Architecture:** Keep the existing page-level virtualizer and header-alignment correction. Treat album-drawer navigation as a deterministic instant jump on both measured and stale-measurement paths, while leaving photo-focus scrolling unchanged.

**Tech Stack:** Vue 3, TypeScript, TanStack Virtual 3.13.23, Vitest, Playwright

## Global Constraints

- Run repository tasks through `mise run <task>`.
- Do not edit generated files under `frontend/src/client/`.
- Preserve page-level virtualization and bounded mounted media.
- Use `rem`, not `px`, except for hairlines, outlines, and optical nudges.
- Do not add code comments unless they explain a hidden constraint.

---

### Task 1: Make nav jumps deterministic

**Files:**
- Modify: `frontend/tests/components/AlbumViewer.test.ts`
- Modify: `frontend/src/components/AlbumViewer.vue`

**Interfaces:**
- Consumes: `useActiveSection().scrollToSection(key)` and TanStack `scrollToIndex(index, options)`.
- Produces: chapter header navigation that uses `behavior: "instant"` even when the target measurement is stale.

- [ ] **Step 1: Write the failing stale-measurement regression test**

Extend the `useWindowVirtualizer` mock with shared `scrollToIndex` and `measurements` variables. Add a test that mounts an album whose only visible header is `cover-front`, sets `measurements` to an empty array, calls `scrollToSection("chapter-chapter-1-cover-front")`, and asserts:

```ts
expect(scrolled).toBe(true);
expect(scrollToIndex).toHaveBeenCalledWith(0, {
  align: "start",
  behavior: "instant",
});
```

- [ ] **Step 2: Run the test and verify the expected failure**

Run: `mise run test:frontend -- tests/components/AlbumViewer.test.ts`

Expected: FAIL because the fallback currently passes `behavior: "smooth"`.

- [ ] **Step 3: Implement the instant nav jump**

In `scrollToVIdx`, keep the direct measured offset path. For `correctForHeader` requests:

```ts
programmaticScrolling.value = true;
if (scrollClearTimer) clearTimeout(scrollClearTimer);
scrollClearTimer = setTimeout(clearProgrammaticScroll, 800);

if (item) {
  window.scrollTo({ top: target, behavior: "instant" });
} else {
  virtualizer.scrollToIndex(idx, {
    align: "start",
    behavior: "instant",
  });
}
correctScrollTarget(idx);
return;
```

Change the two header-correction `window.scrollBy` calls to `behavior: "instant"` as well. Do not change the non-nav smooth path used by photo focus.

- [ ] **Step 4: Run the component regression test**

Run: `mise run test:frontend -- tests/components/AlbumViewer.test.ts`

Expected: PASS, including the new stale-measurement test.

- [ ] **Step 5: Commit the focused change**

```bash
git add frontend/tests/components/AlbumViewer.test.ts frontend/src/components/AlbumViewer.vue
mise exec -- git commit -m "fix(editor): jump directly to chapter pages"
```

### Task 2: Cover the full split-and-jump workflow

**Files:**
- Modify: `frontend/e2e/large-album-performance.test.ts`

**Interfaces:**
- Consumes: chapter split controls and `[data-nav-section="chapter-chapter-3-cover-front"]`.
- Produces: browser-level protection for the reported workflow and bounded mounted media.

- [ ] **Step 1: Add the multi-chapter E2E regression**

Use the existing 240-step fixture. Split the first chapter, split the new second chapter, click the third chapter's cover row, and assert:

```ts
await expect
  .poll(() => page.evaluate(() => window.scrollY))
  .toBeGreaterThan(beforeScrollY + 10_000);
await expect(page.locator('[data-nav-section="chapter-chapter-3-cover-front"]'))
  .toHaveClass(/visible/);
await expect.poll(() => page.locator("[data-media]").count()).toBeLessThan(120);
```

- [ ] **Step 2: Run the focused E2E test against the source build**

Because port 5173 is occupied by the production Docker frontend, create a temporary
Playwright config that starts Vite on port 5174 with `reuseExistingServer: false`.
Run:

```bash
mise run test:e2e -- --config playwright.local-5174.config.ts \
  large-album-performance.test.ts --grep "chapter cover" --workers=1
```

Delete the temporary config after the source-build checks.

Expected: PASS with the later chapter cover active and fewer than 120 mounted media nodes.

- [ ] **Step 3: Commit the E2E regression**

```bash
git add frontend/e2e/large-album-performance.test.ts
mise exec -- git commit -m "test(editor): cover chapter navigation regression"
```

### Task 3: Verify and prepare the pull request

**Files:**
- Delete: `docs/superpowers/specs/2026-07-15-chapter-nav-instant-jump-design.md`
- Delete: `docs/superpowers/plans/2026-07-15-chapter-nav-instant-jump.md`

**Interfaces:**
- Consumes: all changes from Tasks 1 and 2.
- Produces: a clean PR containing only the runnable fix and regression tests.

- [ ] **Step 1: Remove one-off planning artifacts**

Delete the design and plan files so git history remains the archive and the repository contains no dead support material.

- [ ] **Step 2: Run complete relevant verification**

Run:

```bash
mise run test:frontend
mise run test:e2e
mise run lint:frontend
mise run deadcode:frontend
```

Expected: all commands exit 0 with no test failures, lint errors, or dead-code findings.

- [ ] **Step 3: Commit cleanup**

```bash
git add docs/superpowers
mise exec -- git commit -m "chore: remove completed implementation notes"
```

- [ ] **Step 4: Review the final diff against updated main**

Run:

```bash
git diff --check main...HEAD
git diff --stat main...HEAD
git log --oneline main..HEAD
```

Expected: only `AlbumViewer`, its component test, and the large-album E2E test differ from `main`.

- [ ] **Step 5: Push and open the PR**

```bash
git push -u origin codex/fix-chapter-nav-freeze
gh pr create --base main --head codex/fix-chapter-nav-freeze
```

The PR description must include the confirmed fallback cause, the instant-jump fix, and test evidence.
