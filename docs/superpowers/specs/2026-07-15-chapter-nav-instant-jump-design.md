# Chapter Navigation Instant Jump Design

## Problem

Clicking a chapter cover in the editor navigation can freeze the page after an album has been split into chapters. The normal measured path already uses a direct window scroll, but a temporarily unavailable virtualizer measurement falls through to `scrollToIndex` with smooth behavior.

TanStack Virtual's current documentation describes additional measurement work during smooth scrolling, and TanStack issue #1001 records repeated reconciliation when a distant target is outside the mounted range. Wanderbound uses version 3.13.23, whose reconciliation loop can continue for up to five seconds.

## Confirmed Boundary

Production bundle `be2dabc` contains the same fallback. Chromium and Firefox tests with 240 and 2,000 steps confirm that the measured direct-jump path stays responsive and keeps mounted media bounded. The unsafe behavior is isolated to the missing-measurement fallback after the chapter render plan changes.

## Options

1. Make nav requests explicit instant jumps on both measured and fallback paths. This keeps virtualization and the existing header correction. Recommended.
2. Wait for another render tick and retry the measurement. This preserves animation but retains timing sensitivity and adds navigation latency.
3. Upgrade or replace the virtualizer. This expands dependency scope and does not remove the application-level need for deterministic nav jumps.

## Design

Navigation from the album drawer to a page is a jump operation. `AlbumViewer` will mark the jump as programmatic, cancel any active virtualizer reconciliation, and use `behavior: "instant"` for both the direct window scroll and the `scrollToIndex` fallback. The existing two-frame header correction will also use instant scrolling.

Photo-focus restoration and other non-nav scroll callers retain their current behavior.

## Tests

- A component regression test will provide a stale virtualizer measurement cache and verify that chapter cover navigation uses an instant indexed jump instead of smooth scrolling.
- The large-album E2E fixture will split a fresh album into multiple chapters, click a later chapter cover, verify that the target appears, and confirm that mounted media remains bounded.
- Frontend unit, E2E, lint, and build checks will run before the pull request is opened.

## Sources

- TanStack Virtualizer API: https://tanstack.com/virtual/latest/docs/api/virtualizer
- TanStack Virtual issue #1001: https://github.com/TanStack/virtual/issues/1001
