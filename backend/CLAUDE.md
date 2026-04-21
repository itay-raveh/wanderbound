# Backend

See @mise.toml - relevant tasks: `test:backend`, `lint:backend`, `format:backend`, `db:migrate`.

## Architecture

Routes handle HTTP concerns only. Logic modules own business rules. Services wrap external APIs.

### GPS Segments (logic/spatial/segments.py)

5-stage pipeline: Ingest → Label → Absorb → Validate → Emit.
Speed thresholds: hike ≤ 6.5 km/h, flight ≥ 200 km/h + 100 km distance.
Pre-computed at user creation, stored in DB. Albums read from DB (no on-the-fly computation).

### PDF Generation (logic/pdf.py)

Playwright Chrome → loads frontend `/print/:aid` → waits for `__PRINT_READY__` → streams PDF via CDP.
Memory-aware concurrency: 512MB baseline + 768MB per render.

## Non-Obvious Patterns

- `PydanticJSON` TypeDecorator: JSON columns round-trip through Pydantic validation. Alembic renders as `sa.JSON()`.
- `all_optional()`: makes any model PATCH-friendly (all fields Optional).
- `TokenStore[T]`: temporary download URLs with TTL + eviction callbacks (PDF, exports).
- SSE reconnect: `ProcessingSession` replays all past events to reconnecting clients.
- Activity debouncing: writes to DB every 1h/user via bounded `OrderedDict` (1024 entries).
- Session opened only for DB writes - reads use the session cookie but don't start a DB transaction.
- Upload security: magic-byte MIME checks, path traversal detection, symlink rejection, decompression bomb limits.
- External API services: one `http_client()` factory in `core/http.py` (SQLite cache + retries + optional `AsyncLimiter` rate limit). All clients are built at startup by `lifespan_clients()` in `core/http_clients.py`, stored on `app.state.http`, and injected into routes via the `get_http_clients` dependency. Services take `httpx.AsyncClient` params - no module-level accessors.
- Mapbox matching: `services/mapbox.py` (API client) + `logic/route_matching.py` (RDP, haversine). Density-based API selection, auto-match on first segment-points request. Results stored in `segment.route`.

## DB Conventions

- Composite PKs on segment: `(uid, aid, start_time, end_time)`.
- `Album.colors`: country → hex, auto-computed via CIELAB Delta-E to minimize collisions.
- Alembic + PostgreSQL enums: `alembic-postgresql-enum` handles CREATE/DROP TYPE automatically. Never manually edit generated migrations.

## Testing

See @.claude/rules/testing.md for conventions. Backend-specific: in-memory async SQLite with transaction rollback.
