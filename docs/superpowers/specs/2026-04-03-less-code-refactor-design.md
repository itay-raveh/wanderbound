# Less Code Refactor

Codebase-wide pass to reduce code through deduplication, decomposition, and targeted package replacement. Current codebase: ~5,400 backend + ~11,500 frontend (non-generated) = ~17,000 lines.

## 1. Query Factory

**Files:** `frontend/src/queries/useAlbumQuery.ts`, `useMediaQuery.ts`, `useStepsQuery.ts`, `useSegmentsQuery.ts`, `usePrintBundleQuery.ts`

Five query files are byte-for-byte identical except the function name and API import. Each is 17 lines following this pattern:

```ts
export function useXyzQuery(aid: Ref<string | null>) {
  return useQuery({
    key: () => queryKeys.xyz(aid.value),
    query: async () => {
      if (!aid.value) throw new Error("No album selected");
      const { data } = await readXyz({ path: { aid: aid.value } });
      return markRaw(data);
    },
    enabled: () => !!aid.value,
    staleTime: STALE_TIME,
  });
}
```

**Change:** Add a `createAlbumQuery` factory to `keys.ts`. Each query becomes a one-liner export. Delete the 5 individual files.

**Not touched:** `useSegmentPointsQuery` (takes extra params), `useUserQuery` (no album ID, has formatting helpers). These stay as-is.

**Savings:** ~65 lines, 5 files deleted.

## 2. Shared Components

### 2a. SegmentedControl.vue

**Duplication:** UserMenu.vue (light/dark toggle, distance toggle, temperature toggle) and AlbumNav.vue repeat `.seg-track` + `.seg-btn` pattern — ~40 lines of template + ~40 lines of CSS per usage.

**Change:** Extract `SegmentedControl.vue` component:

```vue
<SegmentedControl v-model="value" :options="[
  { label: 'km', value: true, icon: matIcon },
  { label: 'mi', value: false },
]" />
```

Props: `modelValue`, `options: { label, value, icon? }[]`, `compact?: boolean`.

### 2b. ProgressBar.vue

**Duplication:** TripTimeline.vue and StepMetaPanel.vue both implement `.progress-track` + `.progress-fill` with identical CSS (height, border-radius, color-mix background, transform-origin transition).

**Change:** Extract `ProgressBar.vue`:

```vue
<ProgressBar :progress="0.7" />
```

Props: `progress: number` (0-1).

**Savings:** ~80-100 lines across 4+ files, 2 new small components added (~50 lines total).

## 3. AlbumNav Decomposition

**File:** `frontend/src/components/editor/AlbumNav.vue` (1,147 lines)

This file is too large. Script: 391 lines, template: 206 lines, CSS: 549 lines. Split into focused sub-components.

### 3a. useDateRangePicker composable

**Duplication:** The date-picker-with-draft-state pattern appears twice — once for the step filter (lines 74-109) and once for map ranges (lines 249-278). Both maintain: draft ref, popup ref, computed model, open handler (copies model to draft), close handler (parses draft back to mutation).

**Change:** Extract `useDateRangePicker(toModel, onClose)` composable returning `{ draft, model, open, close, popupRef }`.

**Savings:** ~35 lines of genuine dedup.

### 3b. Sub-components

Extract these components from AlbumNav:

| Component | Responsibility | Lines moved |
|---|---|---|
| `NavDateFilter.vue` | Filter chip + popup + excluded-steps computation | ~130 |
| `NavMapRanges.vue` | Map ranges chip + popup + confirm dialog | ~140 |
| `NavCountryGroup.vue` | Expansion item: header (flag, name, dates, visibility toggle) + entry list | ~120 |
| `NavStepItem.vue` | Step entry row: thumb, name, date, visibility toggle | ~90 |
| `NavMapItem.vue` | Map entry row: icon, inline date editor popup, delete button | ~110 |

**AlbumNav becomes an orchestrator** (~250-300 lines): computes `groups` from props, renders album selector + header items, delegates to sub-components. The scroll-sync watchers and `openGroupKey` state stay in AlbumNav since it coordinates across groups.

`makeRefCache` (lines 296-312) moves to `utils/refCache.ts` — it's a generic utility.

**Net lines:** Approximately code-neutral (+20-30 for prop/emit boilerplate), but AlbumNav goes from 1,147 to ~250-300 lines.

## 4. LandingImage Component

**File:** `frontend/src/pages/LandingView.vue` (693 lines)

The `<picture>` + `<source>` + `<img>` pattern repeats 5 times with only the image name and mode changing:

```html
<picture>
  <source :srcset="srcset('cover')" sizes="320px" type="image/webp" />
  <img :src="`/landing/cover-${mode}.jpg`" alt="" class="..." />
</picture>
```

**Change:** Extract `LandingImage.vue`:

```vue
<LandingImage name="cover" :mode="mode" class="hero-card-img" />
```

Props: `name: string`, `mode: 'light' | 'dark'`. Component encapsulates the srcset/source/img boilerplate.

**Not extracted:** Feature "band" sections — they differ enough in structure that a component would just shuffle complexity.

**Savings:** ~40 lines.

## 5. Auth Route Consolidation

**File:** `backend/app/api/v1/routes/auth.py` (140 lines)

Two identical endpoints delegate to the same `_authenticate` function:

```python
@router.post("/google")
async def auth_google(body, request, session):
    return await _authenticate(body.credential, "google", request, session)

@router.post("/microsoft")
async def auth_microsoft(body, request, session):
    return await _authenticate(body.credential, "microsoft", request, session)
```

**Change:** Merge into a single parameterized endpoint:

```python
@router.post("/{provider}")
async def authenticate(provider: AuthProvider, body, request, session):
    return await _authenticate(body.credential, provider, request, session)
```

FastAPI validates `provider` against the enum automatically. Also rename `Provider` to `AuthProvider` in `models/user.py` for clarity (it's a `Literal["google", "microsoft"]` used only in auth context).

**Savings:** ~5 lines.

## 6. Backend Helpers

### 6a. PATCH Update Helper

**Files:** `albums.py` (2 locations), `users.py` (1 location)

Three routes repeat:

```python
obj.sqlmodel_update(update.model_dump(exclude_unset=True))
session.add(obj)
await session.commit()
await session.refresh(obj)
```

**Change:** Extract `apply_update(session, obj, update)` to `api/v1/deps.py`.

**Savings:** ~9 lines.

### 6b. Async yield_completed Helper

**Files:** `processing.py`, `layout/builder.py`, `services/open_meteo.py`

Three files use the same `asyncio.as_completed` → yield pattern:

```python
for coro in asyncio.as_completed(coros):
    yield await coro
```

**Change:** Extract `yield_completed()` async generator to `core/async_helpers.py`.

**Savings:** ~10 lines.

## 7. Test Improvements

### 7a. Parametrize Auth Tests

**File:** `backend/tests/test_auth.py`

`TestAuthGoogle` and `TestAuthMicrosoft` share 3 identical test methods: `test_invalid_jwt`, `test_new_user_returns_null`, `test_existing_user_returns_user`. Microsoft keeps its 3 extra tests (bad issuer, not configured, name fallback) in a separate class.

**Change:** Parametrize the 3 shared tests over `(provider, jwks_client, client_id_setting)`.

**Savings:** ~25 lines.

### 7b. Consolidate Test Fixtures

**File:** `backend/tests/test_albums.py`

`_insert_album`, `_insert_step`, `_insert_segment` (~60 lines) are defined inline. These are reusable across test files.

**Change:** Move to `conftest.py` as fixtures or shared helpers.

**Savings:** ~20 lines (helpers still exist, but centralized and not duplicated if other tests need them).

## 8. Flight Arc Package Replacement

**File:** `frontend/src/components/album/map/mapSegments.ts`

`buildFlightArc` (lines 69-99, 30 lines) manually computes a quadratic Bezier arc between two geographic points. `@turf/bezier-spline` is a well-maintained package (turf is already a dependency — 5 turf packages in use) that creates smooth curves from LineStrings.

**Change:** Replace `buildFlightArc` with:

```ts
import bezierSpline from "@turf/bezier-spline";
import { lineString } from "@turf/helpers";

function buildFlightArc(startLon, startLat, endLon, endLat): [number, number][] {
  const midLon = (startLon + endLon) / 2;
  const midLat = (startLat + endLat) / 2;
  const dx = endLon - startLon, dy = endLat - startLat;
  const dist = Math.sqrt(dx * dx + dy * dy);
  const offset = dist * 0.2;
  const controlLon = midLon + (dy / dist) * offset;
  const controlLat = midLat - (dx / dist) * offset;

  const curved = bezierSpline(
    lineString([[startLon, startLat], [controlLon, controlLat], [endLon, endLat]]),
    { resolution: 10000 },
  );
  return curved.geometry.coordinates as [number, number][];
}
```

**Trade-off:** Catmull-Rom spline (turf) vs hand-rolled quadratic Bezier. Visual curve shape will differ slightly. The midpoint calculation for the flight icon stays as-is (computed from the arc coordinates).

**Savings:** ~15-20 lines. More importantly: replaces custom math with a maintained library.

## Summary

| Section | What | Net lines saved |
|---|---|---|
| 1. Query factory | 5 identical files to factory | ~65 |
| 2. Shared components | SegmentedControl + ProgressBar | ~80-100 |
| 3. AlbumNav decomposition | 6 sub-components + composable | ~35 (dedup) + restructure |
| 4. LandingImage | Extract repeated picture pattern | ~40 |
| 5. Auth route | Merge + rename AuthProvider | ~5 |
| 6. Backend helpers | apply_update + yield_completed | ~19 |
| 7. Test improvements | Parametrize + consolidate fixtures | ~45 |
| 8. Flight arc | Replace with @turf/bezier-spline | ~15-20 |
| **Total** | | **~305-330 net lines** |

AlbumNav restructured from 1,147 to ~250-300 lines (code-neutral but dramatically more readable).

## Design Decisions

- **Module-level composable state stays.** No Pinia migration — module-level refs are idiomatic Vue 3 and less code.
- **No new dependencies except `@turf/bezier-spline`** (turf already in use, minimal bundle impact).
- **Mutations stay separate.** The 3 mutation files (album, step, user) differ enough in cache update strategy and undo behavior that a factory would add complexity.
- **SSE wrappers stay as-is.** `usePdfExportStream` and `useDataExport` are properly factored configs for `useSseDownload`, not duplications.
- **date.ts stays custom.** The functions are Quasar-format-specific (QDate ↔ ISO conversion). No package handles this.
