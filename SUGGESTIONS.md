# Suggestions

## 2025-03-15 — Eliminate `_visual_length` / text-layout duplication across backend and frontend

**Status:** `DONE` — Resolved via DOM-measured text layout instead of the proposed backend approach. Deleted `_visual_length`, `_is_long_description`, and all "Must match" constants from both backend (`builder.py`) and frontend (`usePageDescription.ts`). Backend now always includes cover in pages; frontend measures text fit using hidden DOM containers (`useTextMeasure.ts`) and decides layout type at render time. Zero duplication, self-adjusting to CSS changes.

**Files changed:** `builder.py`, `useTextMeasure.ts` (new), `AlbumViewer.vue`, `StepEntry.vue`, `StepMainPage.vue`, `StepMetaPanel.vue`. `usePageDescription.ts` deleted.

---

## 2025-03-15 — Add PDF render concurrency cap

**Status:** `DONE`

**Problem:** `render_album_pdf` in `backend/app/logic/pdf.py` creates a new Chromium browser context per request with no concurrency limit. Two simultaneous PDF exports both load all album images, Mapbox tiles, and fonts into separate Chromium processes. This can easily exhaust memory on the server (each context uses 200-500MB).

**Proposed fix:** Add `_pdf_semaphore = asyncio.Semaphore(1)` in `pdf.py` and `async with _pdf_semaphore:` around the render body. This serializes PDF generation. If a second request arrives while one is rendering, it waits rather than OOMing the server.

**Files affected:** 1 — `pdf.py`

---

## 2025-03-15 — Lazy section scroll performance (WebGL context leak)

**Status:** `DONE` — Resolved via mount-once + `content-visibility: auto` instead of bidirectional unmounting. The bidirectional approach (mount/unmount on scroll) caused severe jank from destroying and recreating entire component trees. Now sections mount once and stay in the DOM; the browser natively skips rendering off-screen sections via `content-visibility: auto` with `contain-intrinsic-height` for stable scroll positioning. IntersectionObserver uses the actual scroll container (`.viewer-col`) as root for reliable pre-loading. Maps use `eager: true` so they mount immediately. WebGL context count is bounded by the number of map sections per album (typically <16).

**Files changed:** `LazySection.vue`, `EditorView.vue`, `useScrollContainer.ts` (new), `App.vue`.

---

## 2025-03-15 — Strip unused `time` field from segment points in API response

**Status:** `REJECTED` — Not worth the extra model; payload difference is negligible.

**Problem:** Every `Segment` in the `AlbumData` response includes `points: list[Point]` where each `Point` has `{lat, lon, time}`. The frontend (`mapSegments.ts`) only reads `p.lon` and `p.lat` — `time` is never used. For a hike segment with 2,000 points, the `time` field adds ~20KB of unused JSON. Across 50 segments this is 200KB+ of wasted bandwidth on every album load.

**Proposed fix:** Create a `SegmentPoint` schema with only `lat` and `lon` for the API response. Keep the full `Point` (with `time`) in the database for future use. This is a response-shape change, not a schema change.

**Files affected:** ~3 — `segment.py` (add response model), `albums.py` (use it in response), `polarsteps.py` or a new schema

---

## 2025-03-15 — Progressive map matching (render GPS first, then matched geometry)

**Status:** `DONE`

**Problem:** In `mapSegments.ts`, `drawSegmentsAndMarkers` awaits `Promise.all(matchingTasks)` before the function returns and `fitBounds` is called. For segments requiring 5+ map-matching API chunks (p99 latency 1-2s each), the map hangs with no content for several seconds after tiles load.

**Proposed fix:** Draw raw GPS coordinates immediately as a preliminary line layer, then replace each segment's geometry progressively as each matching chunk resolves. This gives users an instant (approximate) map that refines itself. The raw GPS is already available in `segment.points`.

**Files affected:** ~2 — `mapSegments.ts`, `mapMatching.ts`

---

## 2025-03-15 — Sign the auth cookie

**Status:** `PENDING`

**Problem:** The `uid` cookie is a plain integer (the Polarsteps user ID). Anyone who knows or guesses a user ID can authenticate as that user by setting `document.cookie = "uid=42"`. While `httponly` and `samesite` flags (just added) prevent JavaScript access and CSRF, the cookie value itself carries no proof of authentication — there's no server-side secret involved.

**Proposed fix:** Use `itsdangerous.URLSafeSerializer` (already a transitive dep via Flask ecosystem, or add directly — 50KB, well-maintained) to sign the user ID with a server-side secret from `settings.SECRET_KEY`. The cookie becomes `uid=<signed_token>`. `UserDep` in `deps.py` verifies the signature before trusting the user ID. This makes cookie forgery impossible without the server secret.

**Files affected:** ~3 — `config.py` (add SECRET_KEY), `users.py` (sign on set), `deps.py` (verify on read)

---

## 2025-03-15 — Reduce Uvicorn workers to 1 (eliminate redundant Chromium browsers)

**Status:** `DONE`

**Problem:** The production `CMD` in `backend/Dockerfile` runs Uvicorn with `--workers 3`. Each worker is a separate process that runs the FastAPI lifespan, which launches a Chromium browser instance via Playwright (`main.py:32`). This means 3 Chromium browsers are running simultaneously, consuming ~600MB–1.5GB of RAM collectively — for a feature (PDF export) used once per album editing session. Since all endpoints are `async def` and blocking work is offloaded to `asyncio.to_thread()`, a single worker handles concurrent I/O efficiently without multiple processes.

**Proposed fix:** Remove `--workers 3` from the Dockerfile CMD (Uvicorn defaults to 1 worker). This cuts Chromium memory usage by ~66%. Combined with the PDF semaphore suggestion, a single worker with serialized PDF rendering handles all traffic without risk of OOM. If CPU-bound throughput becomes an issue later (e.g., image processing), the solution is to move that work to a task queue rather than adding Uvicorn workers.

**Files affected:** 1 — `backend/Dockerfile`
