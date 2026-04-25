# Backend

Routes handle HTTP concerns only. Logic modules own business rules. Services wrap external APIs.

## Non-Obvious Constraints

- GPS segments are precomputed at user creation and stored in DB. Albums read
  segments from DB, not by recomputing on demand.
- PDF rendering uses Playwright Chrome, waits for `window.__PRINT_READY__ === true`,
  streams via CDP, and is memory-concurrency limited.
- `PydanticJSON` columns round-trip through Pydantic validation and render as
  `sa.JSON()` in Alembic.
- External API clients are built by `lifespan_clients()`, stored on
  `app.state.http`, and injected into routes via `HttpClientsDep`. Services take
  explicit `httpx.AsyncClient` params - no module-level client accessors.
- Composite PKs on segment: `(uid, aid, start_time, end_time)`.
- PostgreSQL enums are managed by `alembic-postgresql-enum`. Do not hand-edit
  generated enum DDL.
- Tests use FastAPI `AsyncClient` with in-memory async SQLite and transaction
  rollback.
