---
paths:
  - "**/*test*"
  - "backend/tests/**"
  - "frontend/tests/**"
---

# Testing Conventions

## Regression Tests

After every bugfix, write a test that reproduces the original bug.
The test must fail without the fix and pass with it. No exceptions.

## Scope

Run only the tests relevant to the change:
- Python changes → `mise run test:backend`
- Vue/TS changes → `mise run test:frontend`
- API contract or cross-cutting changes → `mise run test:e2e`

## Backend (pytest)

- Markers: `@pytest.mark.unit` (no IO/DB), `@pytest.mark.integration`
- Fixtures in conftest: async SQLite engine, session with rollback, ASGI test client
- mock_jwt() for OAuth token mocking, create_test_jpeg() for image fixtures
- pytest-asyncio auto mode. pytest-randomly for ordering.

## Frontend (vitest)

- Environment: happy-dom (vitest.config.ts)
- Mock APIs with MSW handlers (tests/setup.ts)
- Mount components with @vue/test-utils
- Test composables via wrapper components or direct invocation
