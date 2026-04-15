# Testing Philosophy

"Write tests. Not too many. Mostly integration."

Every test must earn its place. A test that never fails is dead weight. A test that breaks on refactor but not on bugs is worse - it erodes trust. The goal is **confidence per test**, not coverage percentage. 50 tests guarding real boundaries beat 200 tests nobody trusts.

## The question before every test

**"If I had zero tests and wrote this feature from scratch, would I write this test?"**

If the answer is "no, I'd just see it in the browser" or "no, the integration test already covers this" - don't write it. If an existing test fails this question, delete it.

## Ruthless pruning

Tests are not sacred. Treat the test suite as a living tool that requires both addition and subtraction:

- **After every feature or refactor**, look at the tests you touched. Did any break for the wrong reason (structure change, not behavior change)? Delete them.
- **Tests that duplicate higher-layer coverage** are redundant. If an E2E test covers the same behavior, the unit test adds nothing.
- **Tests that verify default values** ("starts in idle state", "starts with null") are worthless. If a ref's initial value is wrong, you'll know instantly.
- **Tests that verify wiring** ("press X → spy Y called") test that the code does what the code says. They pass when the app is broken and break when the app is fine.
- **Tests that mock the thing they're testing** (mocking a library to test a wrapper around that library) give zero confidence.
- **"Renders without crashing" tests** catch nothing that opening the page wouldn't catch.

When in doubt, delete the test. You can always write a better one.

## Choosing the right layer

### Unit tests - only for computation

Unit tests earn their keep when they test **a pure function that takes input and returns output** where the value is in the edge cases.

**Write unit tests for:**
- Math and algorithms: DPI calculation, color contrast, geo distance, layout distribution
- Data transformations: `buildStepLayout`, `parseGpsEdges`, `enforceOrientationOrder`, `filterCoverFromPages`
- Payload builders: `unusedUpdatePayload`, `coverUpdatePayload` - contract boundaries
- Complex branching: segment classification, boundary splitting, text line-breaking
- Parsing and formatting: date formatting with timezone edge cases, locale resolution with fallback chains

**Never write unit tests for:**
- State machine transitions observable through the UI (focus/blur, undo/redo, drag state). These give false confidence - they test that the code does what the code does, not that the user sees the right thing.
- Anything requiring DOM mocks, timer fakes, or async scheduling fakes. If you're faking the environment, you're testing your mocks.
- Event handler wiring ("key X dispatches action Y"). Test the behavior, not the plumbing.
- Thin wrappers around libraries. If your wrapper breaks, the integration test or the browser will tell you.
- Trivial composables (3-6 lines). If it's too simple to break, don't test it.
- Initial state and default values. If a ref starts at `null`, that's not a test - that's a declaration.

**Litmus test:** does this test require mocking something to work? If yes, either move to integration (MSW) or E2E, or don't test it at all.

### Integration tests - for API and data flow boundaries

The bulk of the Testing Trophy. These test that **multiple real pieces work together correctly** with minimal faking.

- **Frontend**: Vitest + MSW. Test composables and mutations through real query cache behavior with mocked network. Optimistic updates, error rollback, undo stack integration - these are real boundaries where bugs hide. No DOM mocking, no component mounting for wiring checks.
- **Backend**: FastAPI `AsyncClient` + in-memory SQLite with transaction rollback. Mock only truly external services (Mapbox API, OpenMeteo API, Playwright PDF renderer). When mocking external services, test **response parsing and error handling** (contract boundary), not "sends correct headers" (wiring).

### E2E tests - for anything the user touches

If a feature involves **user interaction + async timing + multiple systems** (state + DOM + scroll + keyboard), skip the unit test and go straight to E2E. The photo focus bug proved this: 19 unit tests passed while the app was broken because they tested the state machine synchronously with no DOM, no virtualizer, and no async timing. One E2E test would have caught it.

- Mocked API via Playwright route handlers. Runs every commit.
- **Implementation-agnostic**: assert only what a user observes - `aria-pressed`, `toBeInViewport()`, bounding boxes, DOM element identity. No CSS class checks, no `data-*` attributes, no internal state.
- **Real interactions only**: Playwright `.click()`, `keyboard.press()`, sidebar clicks by visible text. Never JS-dispatch synthetic events.
- **Import shared constants** (like keyboard shortcuts from `shortcutKeys.ts`) so tests don't break when bindings change.
- **Mutation-test new E2E tests**: break the code in subtle ways (swap directions, drop state updates, off-by-one boundaries) and verify the tests catch it. If a mutation survives, the test is too weak - fix it or delete it.
- **Round-trip verification**: forward N + backward N = same position. This catches off-by-one and asymmetric state bugs that one-directional tests miss.

## What NOT to test

- Library behavior (Pydantic validation, SQLModel ORM, Vue reactivity, Quasar components, Pinia Colada cache mechanics)
- Implementation details (internal data structures, private function call order, CSS class application, DOM side effects like style injection)
- State machine internals covered by E2E or integration tests
- Things static analysis already catches (TypeScript types, ESLint rules)
- Coordination code that requires extensive mocking to isolate - if the test needs more mocks than assertions, it's testing the wrong thing at the wrong layer

## Snapshot testing

Only for **contract boundaries with complex serialized output** (segment pipeline shapes, API response schemas). Never for DOM output. If a snapshot test fails and the response is "just update the snapshot", the test is worse than useless - it's a rubber stamp.

## Regression tests

After every bugfix, write a test that reproduces the original bug. The test must fail without the fix and pass with it. No exceptions. Choose the layer that actually would have caught the bug - if the bug was a race condition, a unit test won't reproduce it.

## Test data

- **Unit tests**: synthetic data only. Factory functions build exactly what each test needs.
- **Integration tests**: JSON fixtures from `fixtures/trips/` for real-world regression. Synthetic data for everything else.
- **E2E tests**: shared mock objects from `frontend/tests/fixtures/mocks.ts`.

## Scope

Run only the tests relevant to the change:
- Python changes: `mise run test:backend`
- Vue/TS changes: `mise run test:frontend`
- API contract or cross-cutting changes: `mise run test:e2e`

## Backend conventions

- **File naming**: `test_{module}.py` mirrors the source module it tests.
- **Test classes**: `TestVerb` or `TestFeature` (e.g., `TestBoundarySplit`).
- **Test methods**: `test_condition_produces_outcome` (e.g., `test_flight_segment_rejected`).
- Factory helpers live in `tests/factories.py`. Fixtures live in `conftest.py`.
- pytest-asyncio auto mode. pytest-randomly for ordering.
- syrupy for contract-boundary snapshot testing only.
- pytest-httpx for mocking external HTTP (Mapbox, OpenMeteo) - test response parsing, not request wiring.

## Frontend conventions

- Environment: happy-dom (vitest.config.ts)
- Mock network with MSW handlers (tests/mocks/) - never mock Vue internals
- Mount components with @vue/test-utils only when testing rendering logic with real props
- Shared mock data in `tests/fixtures/mocks.ts`

## E2E conventions

- Tests live in `e2e/`, mocked API, runs every commit
- Shared mock data imported from `tests/fixtures/mocks.ts`
- Custom fixtures in `e2e/fixtures.ts` - `authedPage` (default mocks), `focusPage` (rich multi-step data)
- Locate elements by accessibility attributes (`aria-pressed`, `role`), visible text, or positional locators (`.first()`, `.nth()`) - never by CSS classes or `data-*` attributes
