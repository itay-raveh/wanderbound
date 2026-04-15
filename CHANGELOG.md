# Changelog

All notable changes to this project are documented here.
## 1.0.0 - 2026-04-15

### Bug Fixes

- exclude media from album export JSON dump
- resolve MAPBOX_TOKEN env var mismatch, tune RDP tolerances, add configurable log level
- rebuild segments in reconcile_trip to restore route lines after re-upload
- use uniform white stat numbers on overview page
- restore aria-label and no-op click guard in SegmentedControl
- restore overflow hidden, shimmer animation, and :dir(rtl) in ProgressBar
- extract shared nav SCSS partials and optimize computed
- update LandingView to use merged authenticate endpoint
- address code review findings from simplify pass
- enlarge minimap pin dot and add contrast stroke
- hike boundary drag — lat/lon swap, stale cache, ghost line mismatch
- resolve fonts.json import via @fonts alias for TS + Vite + Vitest
- text layout robustness and font architecture cleanup
- layout algorithm — portrait threshold, sort order, cover exclusion
- map rendering — tile-aware idle detection, canvas fade-in, casing lines
- overview page — widen fact columns and handle text overflow
- block arrow navigation during cross-step scroll transition
- eliminate E2E flakes from parallel execution pressure
- update generate-og-image.ts paths for scripts/ location
- update generate-landing.ts paths for scripts/ location
- resolve script module resolution and dead code detection
- prevent postcss-rtlcss from inverting hero fan in RTL
- remove @pytest.mark.anyio markers conflicting with asyncio auto mode
- patch get_engine in tests so background tasks use SQLite
- stabilize test-backend CI against random test ordering
- make mock_jwt self-contained for Microsoft auth
- install Playwright for og-image generation
- set VITE_FRONTEND_URL in e2e job
- decouple alembic from Settings, make nginx upstream configurable
- make nginx conf.d writable for envsubst
- add writable tmpfs for nginx conf.d in compose
- give Settings sensible defaults, auto-detect storage capacity
- revert alembic env.py to use Settings
- handle missing data dir in storage detection
- generalize mock_jwt client-ID guard for all providers
- make optional env vars non-required in compose
- restore VITE_FRONTEND_URL in CI docker job for Vite build
- default VITE_FRONTEND_URL build arg to prevent empty URL in Vite build
- enable LFS checkout in Publish for demo fixture photos
- install ffmpeg in Publish for demo video probing
- use flat GHCR image names for publish workflow
- use mtime-based staleness check, drop CI job
- update weather icon URL after upstream repo rename
- enable LFS checkout for backend Docker build
- auto-select first album when none saved
- thicken auth button borders for visibility
- prevent stale boundary drag after segment adjustment
- clean up i18n copy (stop-slop, casual Hebrew tone)
- let space and arrow keys control video playback
- unblock PDF export and Sentry error reporting
- pass mapbox token and frontend URL to backend container
- replace CSS alpha gradients with SVG stop-opacity for PDF rendering
- add network timeout and Playwright auto-reconnect
- cancel virtualizer scroll loop on user interaction
- redesign hike map stats pill for PDF and RTL
- add end tick when elevation chart x-axis has a long tail
- allow Microsoft login in nginx CSP connect-src
- retry transient HTTP errors and clean up PDF render counters
- replace em dashes with hyphens, lint auto-fixes
- disable Sentry performance tracing
- add DOMPurify sanitization to legal page
- update stale selectors in landing screenshot script

### Cleanup

- Remove unused photo config types and settings after removing photo_manager

### Documentation

- add less-code refactor design spec
- add less-code refactor implementation plan
- replace testing conventions with Testing Trophy philosophy
- update CLAUDE.md font references for registry-based architecture
- document script organization and generate workflow
- add README badges, fix footer wrapping in RTL
- add SECURITY.md
- add 1px exception to rem-only rule
- consolidate README screenshots and scaling notes
- replace i18n screenshot with photo grid in README
- rewrite privacy policy and terms of service

### Feature

- video handeling

### Features

- Refactor API services with HTTP caching and batch processing, and remove PDF generation.
- Rearchitect map generation to use direct SVG rendering, refactor application settings, and introduce new photo layout strategies
- Implement asynchronous cache and map generation, refactor SVG scaling, and rename asset functions
- Add trip summary and dedicated step page templates, update album generation, and switch font from Renner to Inter.
- Implement dynamic photo grid layouts based on aspect ratios and correctly orient images using EXIF data.
- Add title page functionality with custom title, cover photo, date formatting, and Hebrew text support
- Add trip map page with location path visualization and travel segment detection.
- Add video frame extraction with quality assessment and image similarity-based duplicate detection.
- Implement manual album layout editor with new CLI command, JS/CSS, and backend support for photo IDs and hidden photos, alongside a minor image similarity fix.
- Implement photo registry and enhance editor with cross-step drag-and-drop photo reordering and new page creation.
- Add cx_Freeze build system for installers and improve path handling for static assets.
- efactor editor CSS, and update build configuration to exclude nicegui from zipping and remove gui base.
- Convert static asset paths in templates to session-based URLs using a new Jinja filter.
- Implement weather API fallback strategy and add editor layout persistence via local storage.
- Add new photos and videos across various trips.
- Redesign UI with a new application icon, modernized Quasar styling, and enhanced form and dialog components.
- Add drag-over styling for the add-page container.
- Add video support to unused photos and refactor photo/video item rendering into a new `photo_item.html.jinja` template.
- refactor Album hierarchy to AlbumBase → AlbumMeta → Album
- add segment route field, outlines, steps/segments/points endpoints
- add backend Mapbox map matching with auto-match
- add print-bundle endpoint, update export for direct queries
- add granular frontend queries with markRaw
- lazy segment point loading, render backend routes
- useOverview composable for overview page stats
- add header visibility toggles, rename excluded_steps → hidden_steps
- add safe margin control, move album properties to inspector drawer
- add fonts.json registry with 12 curated Hebrew-capable fonts
- add font generation script and gitignore generated assets
- demo mode — backend endpoints, i18n overlay, user model
- demo mode — frontend flow, auth actions, demo banner
- add demo fixture data (trip photos + metadata via LFS)
- add photo quality DPI warnings and export gate
- add mise tasks for all generators + umbrella generate task
- add CI generate job, ensure guards for build, and fonts staleness check
- add topo contour background to OG image
- inject git tag as frontend version via Docker build arg
- show resource-loading progress during PDF export
- non-blocking inline PDF export progress

### Fetaure

- submaps

### Fix

- Restore original _split_description behavior for two-column layout
- Update imports after image_selector refactoring
- Correct async weather API URL format and add missing API key check
- delete DB records before files in delete_user to prevent orphaned data
- CI workflows trigger on main branch, not master
- update test mocks after _get wrapper removal in open_meteo
- align backend text-length constants with frontend to prevent cover photo layout mismatch

### Miscellaneous

- regenerate OpenAPI client for new data architecture
- cleanup dead references and fix tests for data architecture redesign
- consolidate Alembic migrations into single initial schema
- remove /ship skill and Claude pre-commit hooks
- move export_openapi.py to backend/scripts/
- add cymbal code exploration policy to CLAUDE.md
- update README roadmap
- switch country SVG source to 50m resolution
- add trip JSON fixtures for backend regression tests
- set up Git LFS for demo trip photos
- add syrupy and pytest-httpx dev dependencies
- update README todo list
- make focused photo border more noticeable
- always use bright dot and light stroke on country pin map
- gitignore topo-contours.svg and og-image.png
- remove superseded testing overhaul plan and spec
- add smoke tests against Docker stack
- prepare repo for GitHub
- fix all failing CI jobs
- add yamllint to pre-commit hooks
- switch from Dependabot to Renovate
- add minimumReleaseAge and branch automerge to Renovate
- migrate config renovate.json (#19)
- Update dependency @types/node to v25
- Update dependency postcss-rtlcss to v6
- Update dependency pytest-randomly to v4
- Update dependency @vue/tsconfig to ^0.9.0
- Update dependency marked to v18
- Update dependency @hey-api/openapi-ts to v0.95.0
- Update github actions
- drop deprecated baseUrl and add vue-tsc to lint job
- Update dependency vue-router to v5
- increase minimumReleaseAge to 14 days for automerged patches
- simplify Renovate schedule to every weekend (UTC)
- Update dependency typescript to v6
- add GHCR publish workflow and switch license to AGPL-3.0
- gate on CI success via workflow_run
- bump login-action to v4 and metadata-action to v6
- add Microsoft, Sentry build args
- use slash-separated GHCR image names
- add landing screenshots to Publish, clean up CI env vars
- add mise dev QoL tasks, standardize db:* namespace
- regenerate landing screenshots
- use 1px for hairline borders and outlines
- mark generated files with linguist-generated
- add create-release job to publish workflow

### Modularize

- Extract parse_step_range to cli.py, extract generate_pdf to output/pdf_generator.py
- Extract photo page processing logic to html/photo_pages.py
- Split data_loader.py - move utilities to utils/dates.py, utils/steps.py, utils/paths.py
- Split formatters.py into formatters/date.py, formatters/coordinates.py, formatters/weather.py

### Performance

- preload default body font alongside heading font

### Refactor

- improve code quality and maintainability
- consolidate rate limiting/retry logic and cache system
- suppress Wayland warning once instead of twice
- extract temperature formatting into helper function
- Extract CLI argument parsing into separate cli.py module
- Extract constants into centralized constants.py module
- Add custom exception classes for better error handling
- Extract formatting functions into separate formatters module
- Convert PhotoManager class to functions and add pyproject.toml
- Move all constants into Settings object with sub-models
- Create utility modules for file operations and path helpers
- Add __all__ exports, improve error messages, and add data validation
- Improve standard library usage and add lru_cache for pure functions
- Remove redundant comments that just repeat the code
- Add type aliases and TypedDict for commonly used data structures
- Improve code readability by reducing duplicate get_settings() calls and simplifying conditionals
- Add comprehensive Google-style docstrings to key functions
- Add configuration error handling and input validation to key functions
- Improve progress tracking consistency and remove redundant updates
- Extract photo processing business logic from main.py into photo_processor module
- Simplify complex functions by extracting helper functions
- Add Pydantic field validators to models for data validation
- Extract common API fetch-and-cache pattern into helper functions
- Extract template rendering logic into separate module
- Improve type hints by using TypedDict for step data and photo pages
- Optimize image loading with parallel processing and metadata caching
- Improve type hints by replacing Any types with TypedDict in photo config
- Split html_generator.py into smaller focused modules (asset_management, step_data_preparation, batch_fetching)
- Split image_selector.py into smaller focused modules (ratio, loader, cover, layout, scorer)
- Convert image_selector.py to wrapper module, move compute_default_photos_by_pages to photo/scorer.py
- dissolve catch-all types, fix Video inheritance, remove Point.datetime bloat
- merge Photo/Video into single Media class, replace SegmentBase with NamedTuple
- replace hand-rolled RDP with simplification library
- move mapSegments to utils, extract shared overview color constant
- make useDragState listener registration lazy
- extract useLocalCopy composable for VueDraggable prop sync
- remove dead CSS variables from App.vue theme
- extract _track_iter to deduplicate progress-reporting pattern
- remove dead CSS var reference and unused future import
- inline trivial _get wrapper in open_meteo.py
- remove WHAT comments from main.ts
- simplify redundant nested ternary in useDarkMode
- add cross-reference comments for duplicated THUMB_WIDTHS constant
- remove unnecessary future annotations import from test_layout
- remove WHAT docstrings that restate function names
- remove WHAT docstrings from frontend utilities
- remove decorative section separator comments
- strip remaining decorative separators from source files
- extract duplicated 42% meta panel width into CSS custom property
- remove remaining decorative separators and WHAT docstrings from frontend
- strip all remaining decorative separators across codebase
- make useMapbox self-initializing, eliminating duplicated lifecycle boilerplate
- extract A4 page dimensions into CSS custom properties
- remove redundant math import and dead NODE_ENV build args
- fix sectionPageCount to use visualLength for accurate page estimates
- log actual error content in PDF pageerror handler
- remove last two WHAT comments from backend and frontend
- use stable identity-based keys for sections v-for
- remove WHAT CSS comment from OverviewPage
- extract PDF rendering from album route into dedicated logic module
- move USER_COOKIE constant from API deps to core config
- deduplicate day count in OverviewPage using provided totalDays
- add missing useLocalCopy.ts to ARCHITECTURE.md composables listing
- use kebab-case for albumIds prop in EditorView template
- import GZipMiddleware from fastapi instead of starlette
- remove trailing period from error message for consistency
- use explicit detail= keyword in HTTPException for consistency
- remove unused test dependencies (@vue/test-utils, jsdom)
- remove unused @vue/eslint-config-prettier dependency
- suppress deptry false positive for psycopg driver dependency
- remove WHAT comment from prestart.sh
- remove boilerplate comments from pre-commit config
- remove WHAT comments from backend Dockerfile
- remove WHAT section comments from tsconfig files
- strip boilerplate comments from alembic.ini
- remove stray MJML extension recommendation
- harden auth cookie with httponly + samesite flags, add architectural suggestions
- clean up useTextMeasure with cached() helper and pre-built prefixes
- extract MapSectionControls, colocate map utils, inline dead CSS vars
- use native dir="auto" for RTL, type SSE events, align tokens

### Refactoring

- restructure project into core, data, features, services, and output packages, and add PDF generation
- Consolidate formatting functions into  and reorganize  and  modules.
- remove redundant docstrings from functions
- Remove batching modules and various settings constants, integrate batch fetching into map and weather services, and adopt Pydantic models for weather data.
- migrate to persist-cache decorator for service function results.:
- Round latitude and longitude to two decimal places and remove redundant comments.
- migrate caching to diskcache with async support and coordinate rounding.
- rename `src/app` to `src/psagen` and restructure the UI with new components and pages.
- change media from dict[str, str] to list[Media]
- update useAlbum and components for Media[] type
- EditorView uses granular queries
- AlbumViewer accepts granular props
- PrintView uses usePrintBundleQuery
- extract geo utilities, add Mapbox service layer, enforce WYSIWYG print contract
- align mapbox service with open_meteo patterns, extract shared RateLimitedTransport
- replace IntersectionObserver scroll spy with virtualizer-derived active section
- replace DOM text measurement with Knuth-Plass + Canvas
- overhaul text layout, overview page, and step pages
- replace 5 identical query files with createAlbumQuery factory
- extract SegmentedControl component from UserMenu
- extract ProgressBar component from TripTimeline
- decompose AlbumNav into focused sub-components
- extract LandingImage component from LandingView
- merge auth endpoints into single /{provider} route, rename to AuthProvider
- extract apply_update and yield_completed helpers
- parametrize shared auth provider tests
- move test_albums helpers to shared conftest
- replace custom flight arc Bézier with @turf/bezier-spline
- extract armIdleReady/disarmIdleReady helpers in useMapbox
- extract factory helpers from conftest to factories.py
- use shared factory helpers in test_pipeline.py
- move mapbox-gl mock to __mocks__/ auto-mock convention
- split E2E tests into fast (mocked) and full (real backend) suites
- audit tests against Testing Trophy, add snapshot + shared mocks
- trim redundant tests (lifecycle combos, stdlib wrappers, data validation)
- drop full E2E suite, flatten e2e/ directory
- replace photo focus registry with data-driven navigation
- polish StepMainPage — print fidelity, a11y, typography, RTL
- improve overview page — centered map, fact layout, label row
- derive font config from fonts.json registry
- drop FontName Literal — backend stores font as plain string
- rewrite landing screenshots to use live demo API
- extract page size constants into pageSize.ts
- extract generic ConfirmDialog from DeleteDialog
- consolidate all scripts into scripts/ with consistent naming
- migrate generate_countries.py from os to pathlib
- formalize generate_topo.py with deps block and pathlib
- improve script content quality
- move fonts.json from project root to frontend/
- simplify generate_fonts.py
- eliminate VITE_BACKEND_URL via same-origin API calls
- restructure i18n keys and use linked messages

### Security

- production readiness fixes across security, infra, and CI
- remove unsafe-inline from CSP script-src

### Testing

- prune tests that don't earn their place
- add focusPage E2E fixture and rich mock data
- add photo focus and arrow navigation E2E tests
- add undo/redo and text editing E2E tests
- add E2E regression tests for video keyboard controls

### Polish

- improve cover page typography, token consistency, and a11y
- simplify landing page — remove how-it-works, sharpen tagline
- audit and harden upload page design
- redesign map lines, markers, and drag handles
- switch unused-photos drawer to 2-column grid
