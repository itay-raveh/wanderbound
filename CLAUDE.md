# Project Philosophy

This is a personal project in very early pre-alpha. There are NO users, NO backward compatibility concerns, NO legacy constraints. Every part of this codebase — the schema, the architecture, the module boundaries, the feature design — is open to being rethought and rebuilt from scratch at any time. The question is never "how do I fix what's here" but "what's the right way to build this?"

**Before making large changes, read `ARCHITECTURE.md` for codebase orientation.** Check `SUGGESTIONS.md` for pending architectural proposals (implement any marked `APPROVED`).

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

- **Think top-down, not bottom-up.** Before touching any code, ask: "If I were building this from scratch today, would I design it this way?" If no, redesign it — don't patch it. This applies at every level: the system architecture, the database schema, the module structure, the individual function.
- **Less code is better.** The best change deletes code. An entire module replaced by a library. Five files merged into one. A 200-line feature rewritten in 40 lines with a better approach. Measure improvement in code deleted, not code added.
- **Rewrite over patch.** If a module, feature, or system is built on the wrong foundation, do not layer fixes on top. Rewrite it from scratch with the right design. This is pre-alpha — rewrites are cheap, accumulated patches are expensive.
- **Use the platform and ecosystem.** Prefer built-in language features, standard library functions, and well-known packages over custom implementations. If a mature library does it, delete your version. If the framework has a pattern for it, use that pattern.
- **Idiomatic and canonical.** Write code the way the language/framework community writes it. Follow the "blessed path." If there's a well-known architecture for this kind of app, use it — don't invent a novel one.
- **Single source of truth.** Every value, configuration, constant, or piece of knowledge must live in exactly one place. Derive everything else from that source. This applies to code, config, schema definitions, and documentation.
- **No future-proofing.** Do not add abstraction layers, extension points, plugin systems, or flexibility "for later." Solve today's problem in the simplest way. We will redesign when needs change.
- **No backward compatibility.** There are no users or consumers. Change any interface, rename anything, restructure any module, alter the schema, rewrite any feature. Breaking changes are free.

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

**System level:**
- A service, module, or layer that exists "for separation" but adds no value — merge or delete it
- A schema designed around the code's needs rather than the domain's reality — reshape it
- Data passing through unnecessary transformations, adapters, or serialization steps between layers
- Hand-built infrastructure (auth, caching, queuing, task scheduling, rate limiting) when a standard tool exists
- Artificial file/module separation (types.ts, constants.ts, utils.ts, helpers.ts) that scatters related code — colocate by feature

**Code level:**
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
