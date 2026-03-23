# Architecture

> **AI-facing document.** Keep this current after every structural change - new files, moved modules, changed data flows, added dependencies. This saves full-codebase exploration on every conversation.

## What This App Does

Converts a Polarsteps data export ZIP into a printable photo album (PDF). Users upload their ZIP, the backend processes GPS tracks / weather / elevations / photos, and the frontend renders an interactive album editor that can be exported to PDF via headless Playwright.

## Services (Docker Compose)

```
db          PostgreSQL 18          :5432
backend     FastAPI + Uvicorn      :8000  (runs migrations on startup)
frontend    Vite (dev) / Nginx     :5173 (dev) / :80 (prod)
```

All env vars in root `.env`. Compose reads it via `env_file`. Frontend build-time vars prefixed `VITE_`.

## Directory Layout

```
backend/
  app/
    main.py                 FastAPI app, lifespan (composes domain lifespans from pdf.py + export.py), middleware
    core/
      config.py             Pydantic Settings (reads ../.env), USER_COOKIE constant
      db.py                 Async SQLAlchemy engine, PydanticJSON column type, all_optional helper
      http.py               Shared httpx AsyncClient factory (SQLite cache + retries)
      logging.py            Rich-based access log handler
    api/v1/
      router.py             Mounts auth, users, albums, assets, health routers
      deps.py               SessionDep, UserDep (session-based uid auth), BrowserDep
      routes/
        auth.py             POST /google (Google JWT verification + session), POST /logout
        users.py            POST /upload (create from ZIP), GET, PATCH, DELETE, GET /process (SSE), GET /export (SSE), GET /export/download/{token}
        albums.py           GET /{aid}, GET /{aid}/data, PATCH /{aid}, PATCH /{aid}/steps/{sid}, POST /{aid}/pdf
        assets.py           GET /{aid}/media/{name} (lazy thumbnails + poster extraction), PATCH (video frame re-extract)
        health.py           GET /health (readiness check)
    models/
      weather.py            Weather, WeatherData (stored in step.weather JSON column)
      user.py               User table (SQLModel) + UserUpdate + PSUser (ZIP) + GoogleIdentity
      album.py              Album table + AlbumUpdate + AlbumData response model
      step.py               Step table + StepBase + StepUpdate (name, description, cover, pages, unused)
      segment.py            SegmentKind enum + Segment table (points as PydanticJSON)
      polarsteps.py         Pydantic models for Polarsteps ZIP data + shared types (CountryCode, HexColor, HasLatLon)
      __init__.py            Imports all tables so Alembic sees them
    logic/
      pdf.py                Playwright PDF renderer (browser context, cookies, print emulation)
      upload.py             Extract ZIP -> create User + discover trips -> save to DB
      processing.py         3-phase processing pipeline:
                              elevations -> weather -> layouts/flatten -> DB commit
      session.py            SSE session management: ProcessingSession (background task with
                              event replay), process_stream (per-user session reuse/reconnect)
      export.py             GDPR data export: ZIP generation, SSE events, token management
      reconcile.py          Re-upload reconciliation: scan media, update pages/covers, probe orientations
      eviction.py           LRU storage eviction: delete oldest users' data when disk cap exceeded
      country_colors.py     Assign distinct colors to countries (Delta-E color distance)
      layout/
        __init__.py          Exports Layout, build_step_layout
        builder.py           Photo layout algorithm (portrait/landscape packing into pages)
        media.py             Photo/Video models, ffprobe, ffmpeg frame extraction, on-demand thumbnail generation
      spatial/
        segments.py          GPS segmentation pipeline (ingest -> label -> absorb -> validate -> emit)
        peaks.py             OSM Overpass peak correction for DEM elevations
    services/
      open_meteo.py          Rate-limited Open-Meteo client: DEM elevations + historical weather
    alembic/
      env.py                 Migration runner (renders PydanticJSON as sa.JSON)
      versions/              Migrations: initial tables, steps_ranges/maps_ranges string->JSON, index->date
  data/users/                User upload data (ZIPs extracted here, one folder per user ID)
  tests/                     pytest (392 tests), conftest with shared fixtures (SQLite engine, session, client)
  pyproject.toml             Python 3.14, deps: FastAPI, SQLModel, Polars, Playwright, Pillow, httpx
  logging.json               Uvicorn log config (Rich handlers)

frontend/
  src/
    main.ts                  App bootstrap: Pinia, PiniaColada, Quasar, router, dark mode, API client config
    App.vue                  Root layout, CSS design tokens (--bg, --text, --surface), dark/light themes
    router/index.ts          3 routes: / (editor), /register, /print/:aid
    client/                  Auto-generated by @hey-api/openapi-ts from backend OpenAPI spec
      index.ts               Re-exports all SDK functions + types
      sdk.gen.ts             Typed HTTP functions (createUser, readAlbum, exportPdf, etc.)
      types.gen.ts           TypeScript interfaces matching backend Pydantic models
    pages/
      EditorView.vue         Main editor: header toolbar + album viewer, album selection in localStorage
      RegisterView.vue       Onboarding: ZIP upload -> SSE processing progress -> redirect to editor
      PrintView.vue          Headless render target for PDF: loads album, waits for fonts/images, signals __PRINT_READY__
    queries/
      keys.ts               Query key factory (albums, albumData, user)
      useUserQuery.ts        User data + formatting helpers (distance, temp, elevation, date, locale) + KM_TO_MI, M_TO_FT constants
      useAlbumQuery.ts       Single album fetch
      useAlbumDataQuery.ts   Album steps + segments fetch
      useAlbumMutation.ts    Optimistic album PATCH
      useStepMutation.ts     Optimistic step PATCH (layout + name/description)
      useUserMutation.ts     Optimistic user preferences PATCH
      useVideoFrameMutation.ts  Video poster re-extraction
      useSegmentBoundaryMutation.ts  Hike boundary adjust mutation
    composables/
      useAlbum.ts            provide/inject for AlbumContext (albumId, colors, orientations, tripStart, totalDays)
      useMapbox.ts           Mapbox GL map lifecycle (init, destroy, fitBounds, resize observer, locale)
      useHikeBoundaryDrag.ts Draggable hike segment boundary handles (snap to line, time interpolation)
      useLocale.ts           Locale resolution, vue-i18n setup, locale options list
      useStepLayout.ts       Drag-and-drop wiring for step photo pages, cover, and unused tray
      useDragState.ts        Global drag-in-progress boolean (document-level events)
      useLocalCopy.ts        Writable ref synced to a prop array (needed for VueDraggable v-model)
      useTextMeasure.ts      DOM-measured text layout: short / long / extra-long via hidden containers
      usePrintReady.ts       provide/inject for print mode boolean
      useSseDownload.ts      Shared SSE+download composable factory (state machine, loading overlay, token download)
      useDataExport.ts       SSE consumer for GDPR data export (wraps useSseDownload)
      usePdfExportStream.ts  SSE consumer for PDF export (wraps useSseDownload)
      useProcessingStream.ts SSE consumer for processing progress (phases, trips, errors)
    components/
      AlbumViewer.vue        Master album renderer: computes sections from ranges, renders cover/overview/maps/steps
      LazySection.vue        IntersectionObserver wrapper for lazy-loading album sections
      album/
        albumSections.ts     Section type + buildSections (section ordering), IndexedPage + filterCoverFromPages
        colors.ts            DEFAULT_COUNTRY_COLOR, STAT_COLORS, getCountryColor helper
        EditableText.vue     Inline text editing (single-line contenteditable / multiline dialog), auto print-mode
        CoverPhotoPicker.vue Dropdown grid for selecting cover photos
        CoverPage.vue        Full-bleed cover with date/title overlay (front) or plain image (back)
        MediaItem.vue         Photo (srcset + lazy) / Video (poster + controls + frame scrubber)
        StepEntry.vue         Step container: main page + text pages + photo pages + unused tray, all with drag-and-drop
      album/map/
        MapPage.vue           Overview map with segments + step markers
        HikeMapPage.vue       Hike-focused map with terrain DEM, stats overlay, elevation profile
        ElevationProfile.vue  SVG elevation chart (dist vs elev, gradient fill, axis labels)
        MapSectionControls.vue Delete + date range picker controls for map sections
        mapSegments.ts        Draw GPS segments + step markers on map (flight arcs, hike trails, driving/walking lines)
        mapRouting.ts         GPS trace routing: Map Matching (dense) + Directions (sparse), chunked, cached
        map-segments.css      Marker + flight icon styles for Mapbox GL overlays
      album/overview/
        OverviewPage.vue      Trip summary: stats (days/distance/photos/steps), country strip, extremes, furthest point
        OverviewExtremes.vue  Coldest / hottest / highest step cards
        OverviewFurthestPoint.vue  Distance-from-home widget (Turf.js)
      album/step/
        StepMainPage.vue      Left meta panel + right cover photo or full description
        StepMetaPanel.vue     Country silhouette, location, editable name/description, weather, elevation, progress bar
        StepPhotoPage.vue     Smart photo grid (1-6 photos with orientation-aware layouts)
        StepTextPage.vue      Overflow text continuation page (multi-column)
        CountrySilhouette.vue SVG country outline with location pin
        UnusedSidebar.vue     Draggable unused photos tray
      editor/
        EditorHeader.vue      Top bar with logo + UserMenu, wraps AlbumToolbar via slot
        AlbumToolbar.vue      Trip select, step date ranges, PDF export
        StepDatePicker.vue    Date range picker with country-colored event dots
        UserMenu.vue          Settings: appearance, units, locale, data (re-upload/export), sign out, delete
        DeleteDialog.vue      Confirmation modal for data deletion
      register/
        RegisterHero.vue      Splash header with logo
        RegisterStep.vue      Numbered step container
        DataInstructions.vue  Step 1: download instructions
        ZipUploader.vue       Step 2: file upload (q-uploader -> POST /users)
        UnsupportedBanner.vue Browser compatibility warning
        ProcessingProgress.vue Live processing status with TripTimeline
        TripTimeline.vue      Phase progress visualization (elevations -> weather -> layouts)
    utils/
      media.ts               mediaUrl, mediaSrcset, mediaThumbUrl, posterPath, isVideo, flagUrl, weatherIconUrl, THUMB_WIDTHS, EDITOR_ZOOM, SIZES_FULL, SIZES_HALF
      date.ts                Date utilities: isoDate, parseYMD, parseLocalDate, daysBetween, inDateRange, toQDate/toIso, ymdToIso, qDateNavBounds
    styles/
      fonts.css              Self-hosted Inter + Heebo (Hebrew), font-display: block for PDF
      animations.css         fadeUp, pulse, shimmer keyframes
    countries/
      bounds.json            Country bounding boxes for SVG viewports
  tests/                     Vitest unit tests (happy-dom), helpers, MSW mocks
  e2e/                       Playwright E2E tests (smoke, editor)
  openapi-ts.config.ts       Points to live backend for client generation
  vitest.config.ts           Vitest config (happy-dom, test setup)
  playwright.config.ts       Playwright E2E config
  vite.config.ts             Env from parent dir, Quasar plugin, mapbox-gl manual chunk
  nginx/
    nginx.conf               Prod server: rate limiting, gzip, security headers
    proxy-params.conf        Shared reverse-proxy directives (upstream keepalive)
    security-headers.conf    CSP, X-Frame-Options, MIME sniff, referrer, permissions
```

## Data Flow

### Upload & Processing

```
User uploads ZIP -> POST /users -> extract ZIP to data/users/{uid}/
  -> parse user.json -> discover trip directories -> save User to DB
  -> return UserCreated { user, trips[] }

GET /users/process (SSE) -> ProcessingSession (background task, reconnectable)
  Per trip:
    1. elevations  - Open-Meteo DEM API (batched, 100/request)
    2. weather     - Open-Meteo Archive API (1 call/step, concurrent)
    3. layouts     - read photos/videos from step dirs, build page layouts
       -> flatten media to trip root dir
       -> pick cover photo from local media (landscape preferred)
  Video posters and thumbnails are generated lazily on first request (assets.py).
  -> build_segments (Polars pipeline: GPS -> typed segments)
  -> bulk insert Album + Steps + Segments to DB
```

### Data Export

```
GET /users/export (SSE) -> async ZIP generation in thread
  -> yields ExportProgress (files_done / files_total)
  -> yields ExportDone (token for download)
GET /users/export/download/{token} -> FileResponse (ZIP)
  -> ZIP contains: account.json, per-album JSON (album, steps, segments) + media files
```

### PDF Export

```
POST /albums/{aid}/pdf
  -> Playwright opens /print/{aid} on frontend
  -> PrintView loads album, waits for all images + fonts
  -> sets window.__PRINT_READY__ = true
  -> Playwright captures PDF (A4 landscape, CSS page size, print background)
```

### Album Editing

```
EditorView -> useAlbumQuery + useAlbumDataQuery -> AlbumViewer
  -> AlbumToolbar: PATCH /albums/{aid} (title, subtitle, covers, ranges)
  -> StepEntry: drag-and-drop photos, inline name/description editing -> PATCH /albums/{aid}/steps/{sid}
  -> CoverPage: inline title/subtitle editing -> PATCH /albums/{aid}
  -> All mutations use optimistic updates (Pinia Colada cache)
```

## Database Schema

4 tables, all with CASCADE deletes from User:

```
user
  id (PK)              int (Polarsteps user ID)
  google_sub           str (unique, indexed - Google account identifier)
  first_name, profile_image_url, locale, unit_is_km, temperature_is_celsius
  living_location      JSON (Location: name, detail, country_code, lat, lon)
  album_ids            JSON (list of album ID strings)
  last_active_at       datetime (debounced activity tracking for LRU eviction)

album
  (uid, id) PK         uid FK -> user.id
  title, subtitle, front_cover_photo, back_cover_photo
  steps_ranges         JSON (list[DateRange] - date-based step filtering)
  maps_ranges          JSON (list[DateRange] - map section date ranges)
  colors               JSON (country_code -> hex color)
  media                JSON (media_name -> "p"/"l")

step
  (uid, aid, idx) PK   (uid,aid) FK -> album, uid FK -> user
  name, description, timestamp, timezone_id
  location             JSON (Location)
  elevation            int
  weather              JSON (Weather: day{temp,feels_like,icon}, night{...})
  cover, pages         JSON (layout: cover filename, pages as filename[][])
  unused               JSON (unused filenames)

segment
  (uid, aid, start_time, end_time) PK   (uid,aid) FK -> album
  kind                 enum (flight, hike, walking, driving)
  points               JSON (Point[]: lat, lon, time)
```

## Key Types

### Backend

| Type                      | Location                  | Purpose                                                                                                   |
|---------------------------|---------------------------|-----------------------------------------------------------------------------------------------------------|
| `DateRange`               | `models/album.py`         | `tuple[date, date]` type alias - used for steps_ranges and maps_ranges                                    |
| `Layout`                  | `logic/layout/builder.py` | NamedTuple(cover, pages, orientations) - step photo layout                                                |
| `SegmentKind`             | `models/segment.py`       | Enum: flight, hike, walking, driving                                                                      |
| `SegmentData`             | `models/segment.py`       | NamedTuple(kind, points) - GPS segmentation pipeline output                                               |
| `CountryCode`, `HexColor` | `models/polarsteps.py`    | Annotated string types with validation constraints                                                        |
| `HasLatLon`               | `models/polarsteps.py`    | Structural protocol for objects with lat/lon attributes                                                   |
| `PSTrip`, `PSStep`        | `models/polarsteps.py`    | Polarsteps ZIP data models (not stored in DB)                                                             |
| `Point`, `Location`       | `models/polarsteps.py`    | GPS point (lat, lon, time) and named location with country code                                           |
| `Weather`, `WeatherData`  | `models/weather.py`       | Day/night weather with WMO icon names                                                                     |
| `ProcessingEvent`         | `logic/processing.py`     | Discriminated union: TripStart                                                                            | PhaseUpdate | ErrorData |
| `MediaName`               | `logic/layout/media.py`   | Annotated str with UUID_UUID.(jpg                                                                         |mp4) pattern |
| `Media`                   | `logic/layout/media.py`   | Media metadata (dimensions, orientation, aspect ratio), with `load` (photo) and `probe` (video) factories |

### Frontend

| Type              | Location                        | Purpose                                                               |
|-------------------|---------------------------------|-----------------------------------------------------------------------|
| `AlbumContext`    | `composables/useAlbum.ts`       | Injected context: albumId, colors, orientations, tripStart, totalDays |
| `DescriptionType` | `composables/useTextMeasure.ts` | "short" / "long" / "extra-long" text layout classification            |
| `ProcessingPhase` | Generated from backend          | "elevations" / "weather" / "layouts"                                  |
| All API types     | `client/types.gen.ts`           | Auto-generated from backend OpenAPI schema                            |

## Auth Model

Google Sign-In JWT → Starlette session. `POST /auth/google` verifies the JWT, stores `uid` in the server-side session cookie. `UserDep` in `deps.py` reads `request.session["uid"]` and loads the User from DB.

## External APIs

| API                              | Client                                          | Caching                         | Rate Limit                       |
|----------------------------------|-------------------------------------------------|---------------------------------|----------------------------------|
| Open-Meteo Elevation             | `services/open_meteo.py`                        | SQLite, 30 days                 | 480/min (weighted by batch size) |
| Open-Meteo Archive Weather       | same client                                     | same                            | same limiter                     |
| Overpass (OSM peaks)             | `logic/spatial/peaks.py`                        | SQLite, 30 days (POST body key) | None (low volume)                |
| Mapbox Map Matching + Directions | `components/album/map/mapRouting.ts` (frontend) | In-memory by segment identity   | Per-token limit                  |
| Mapbox GL tiles                  | `composables/useMapbox.ts`                      | Browser cache                   | Per-token limit                  |

## GPS Segmentation Pipeline (`segments.py`)

5-stage Polars pipeline, all vectorized:

1. **Ingest** - merge step waypoints + GPS locations, dedup, remove teleports/spikes, densify slow edges to ~15m
2. **Label** - classify edges: flight (>200 km/h), hike (<6.5 km/h within 4h gap), other
3. **Absorb** - fold noise gaps (<3h, <4km), overnight camps (<1km, <20h), GPS blackouts back into hikes
4. **Validate** - downgrade undersized hikes (<2h, <2km, <1km displacement) and short flights (<100km) to "other"
5. **Emit** - RDP simplify, resolve "other" -> walking/driving by avg speed, stitch consecutive segments

## Photo Layout Algorithm (`builder.py`)

Packs step photos into album pages:
- Split into portraits (aspect ≤ 4:5) and landscapes
- Cover = best portrait (closest to 4:5) or first landscape
- Mixed pages: 1 portrait + 2 landscapes (minimize total page count)
- Portrait pages: batched by 3
- Landscape pages: optimal 4/3 decomposition
- Frontend renders grids in StepPhotoPage with orientation-aware CSS layouts

## Build & Test

All commands via [mise](https://mise.jdx.dev/) (`mise tasks` to list):

```bash
mise run test:backend          # pytest (392 tests)
mise run test:frontend         # vitest
mise run test:e2e              # playwright
mise run lint                  # ruff + ty + eslint
mise run format                # ruff fix + prettier
mise run migrate               # alembic upgrade head
mise run build                 # production frontend build
mise run up                    # docker compose up
```

## CI

Single workflow **ci.yml** with parallel jobs:

- **lint** — ruff check + format, ty check, eslint
- **test-backend** — pytest (in-memory SQLite, no Docker)
- **test-frontend** — vitest (happy-dom)
- **test-e2e** — Playwright E2E tests
- **docker** — build all images
