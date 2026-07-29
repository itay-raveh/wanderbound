# Backend

HTTP routes translate requests and responses. Logic modules own domain rules,
services wrap external APIs, and `logic/workflows/` owns durable DBOS work.

## Constraints

- Use `pathlib`, not `os` or `os.path`.
- The runtime is Python 3.14. `except A, B:` is valid syntax.
- GPS segments are created during trip processing and stored in the database.
  Albums must not recompute them on demand.
- Segments use the composite key `(uid, aid, start_time, end_time)`.
- `PydanticJSON` validates JSON values on database round trips and must render
  as `sa.JSON()` in Alembic migrations.
- PostgreSQL enums are managed by `alembic-postgresql-enum`. Do not hand-edit
  generated enum DDL.
- External HTTP clients come from `lifespan_clients()`, live on
  `app.state.http`, and are injected through `HttpClientsDep`. Services receive
  clients explicitly.
- PDF rendering waits for `window.__PRINT_READY__ === true` and streams through
  CDP under a memory-concurrency limit.
