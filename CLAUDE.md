# Architecture Reference

Read `ARCHITECTURE.md` before exploring the codebase — it maps every file, data flow, and key type. **After any structural change** (new/moved/deleted files, changed data flows, new dependencies, schema changes), update `ARCHITECTURE.md` to match.

# Project Philosophy

This is a personal project in very early pre-alpha. There are NO users, NO backward compatibility concerns, NO legacy constraints. We prefer to redo things correctly from scratch over preserving existing code.

## Tech Stack

Docker, PostgreSQL, Nginx, Vue (frontend), FastAPI (backend).

## Stack-Specific Guidance

**FastAPI:**
- Use Pydantic models for all validation — never hand-roll request/response validation
- Use FastAPI's dependency injection (`Depends()`) — don't build custom DI
- Use `APIRouter` for route organization — don't build custom routers or dispatch logic
- Use built-in `HTTPException` — don't create custom exception class hierarchies
- Use Python type hints as the source of truth — Pydantic, FastAPI, and the IDE all read them
- Use `async def` endpoints with async DB access; don't mix sync and async

**PostgreSQL / SQLAlchemy:**
- Use SQLAlchemy's ORM models as the single source of truth for schema — don't duplicate column definitions in Pydantic models by hand; derive them or keep them in sync
- Use Alembic for migrations — never raw DDL scripts
- Use relationships and foreign keys in the ORM — don't hand-manage joins in application code
- Use parameterized queries always — never f-strings or string concatenation for SQL
- Prefer database-level constraints (unique, check, not-null) over application-level validation

**Vue:**
- Use Composition API (`<script setup>`) — not Options API
- Use composables (`use*` functions) for reusable logic — not mixins or HOCs
- Use Vue Router for routing — don't build custom navigation
- Use Pinia for shared state — don't roll custom stores or event buses
- Use `v-model` and built-in directives — don't reimplement two-way binding
- Colocate components with their route when possible

**Docker / Nginx:**
- Keep Dockerfiles minimal — multi-stage builds, small base images
- Nginx config should be as short as possible — don't duplicate upstream/location blocks
- All environment-specific values via env vars or `.env` files — never hardcoded in Dockerfiles or nginx conf
- Docker Compose as the single source for service topology, ports, and dependencies

## Core Principles

- **Less code is better.** The best refactor deletes code. If something can be achieved in fewer lines without sacrificing clarity, do it.
- **Use the platform and ecosystem.** Prefer built-in language features, standard library functions, and well-known packages over custom implementations. Never hand-roll something that a mature library already does well.
- **Idiomatic and canonical.** Write code the way the language/framework community writes it. Follow the "blessed path." If there's a well-known pattern for something, use it — don't invent a novel approach.
- **Single source of truth.** Every value, configuration, constant, or piece of knowledge must live in exactly one place. Derive everything else from that source. Hunt down and eliminate magic numbers, duplicated constants, and values that are implicitly calculated from other values.
- **No future-proofing.** Do not add abstraction layers, extension points, plugin systems, or flexibility "for later." Solve today's problem in the simplest way. We will refactor when needs change — that is cheap and preferred.
- **No backward compatibility.** There are no consumers of this code. Feel free to change any interface, rename anything, restructure any module. Breaking changes are free.
- **Prefer bold changes over local hacks.** If the right fix requires restructuring a module, changing a function signature across 20 call sites, or deleting an entire file and rewriting it — do that. Do NOT add a workaround, shim, adapter, or compatibility layer.

## Documentation

Code should be self-documenting through clear names, types, and structure. Comments explain WHY, never WHAT.

**Hierarchy (use the lightest level that works):**
1. **No comment needed** (the default) — function name, parameter names, types, and return type tell the full story. Most code should be at this level.
2. **One-line docstring** — when the function name alone leaves ambiguity about intent, a single sentence clarifying the WHY is enough. Example: `"""Retry with backoff because the upstream API rate-limits aggressively."""`
3. **Full docstring** — only for genuinely complex functions: non-obvious algorithms, important preconditions or side effects, tricky edge cases. Keep it short even then.

**Rules:**
- Never comment WHAT the code does — if the code needs a WHAT comment, rename things until it doesn't
- Never leave auto-generated boilerplate docstrings (e.g., `"""Get the user."""` on `get_user()`)
- Never comment out code — delete it; git has history
- TODO comments are acceptable only with a concrete description of what and why, never bare `# TODO`

## Logging

Add logging wherever it helps debugging, monitoring, or understanding system behavior. Keep it clean and useful.

**Rules:**
- Use Python's `logging` module in the backend and `console` methods (or a lightweight wrapper) in the frontend — no custom logging frameworks
- Use appropriate levels: `debug` for development detail, `info` for normal operations worth recording, `warning` for recoverable issues, `error` for failures
- Log messages should be concise and include relevant context (IDs, counts, operation names) — not raw objects or full stack traces at info level
- **Never log secrets, tokens, passwords, PII, or full request/response bodies** — sanitize or omit sensitive fields
- Prefer structured values in log messages (e.g., `logger.info("Created order", extra={"order_id": id, "items": count})`) over f-string prose
- Don't log inside tight loops or hot paths — one log per operation, not per iteration
- Log at boundaries: incoming requests, outgoing calls, DB queries, startup/shutdown, errors, retries

## Anti-Patterns to Actively Eliminate

- Custom utility functions that duplicate standard library or well-known package functionality
- Abstraction layers with only one implementation
- Configuration systems for things that could be constants
- Wrapper types/classes around simple primitives
- "Manager", "Handler", "Service", "Provider" classes that just proxy to one thing
- Enums, constants, or types defined in multiple places or derived from each other implicitly
- Defensive code for situations that cannot happen in this codebase
- Feature flags, toggles, or conditional paths for features that don't exist yet
- Deep inheritance hierarchies or complex generic type parameters when a simple concrete type works
- Magic numbers — any literal value that represents something defined elsewhere or calculable from something else
- Hand-rolled validation when Pydantic does it
- Custom middleware when FastAPI `Depends()` does it
- Raw SQL strings when SQLAlchemy ORM does it
- Options API or mixins in Vue when Composition API and composables do it
- Duplicated port numbers, hostnames, or DB names across Dockerfiles, nginx conf, docker-compose, and app config — define once in `.env` or `docker-compose.yml` and reference everywhere
- Comments that describe WHAT code does — if the code needs a WHAT comment, the code is unclear
- Boilerplate docstrings that restate the function name
- Commented-out code (delete it, git has history)
- Logs that dump raw objects, full request bodies, or sensitive data
- Custom logging frameworks when the standard library works

## Compaction Instructions

When compacting, always preserve: the full list of files modified in this session, any test or build failures encountered, the current refactoring focus area, and any SUGGESTION that was discussed or approved.
