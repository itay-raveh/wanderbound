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
