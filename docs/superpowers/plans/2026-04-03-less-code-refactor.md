# Less Code Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce ~300 lines of duplication across the codebase and decompose AlbumNav.vue (1,147 → ~250-300 lines) into focused sub-components.

**Architecture:** 8 independent refactoring sections: query factory, shared UI components, AlbumNav decomposition, LandingImage extraction, auth route consolidation, backend helpers, test improvements, and flight arc package replacement. Each section is independently testable and committable.

**Tech Stack:** Vue 3, TypeScript, Pinia Colada, Quasar, FastAPI, SQLModel, pytest, @turf/bezier-spline

**Spec:** `docs/superpowers/specs/2026-04-03-less-code-refactor-design.md`

**Run commands:**
- Backend tests: `mise run test:backend`
- Frontend tests: `mise run test:frontend`
- Frontend lint: `mise run lint:frontend`
- Backend lint: `mise run lint:backend`
- Frontend build: `mise run build`

---

## File Map

### Created
- `frontend/src/queries/queries.ts` — `createAlbumQuery` factory + re-exports of all album queries
- `frontend/src/components/ui/SegmentedControl.vue` — reusable segmented toggle
- `frontend/src/components/ui/ProgressBar.vue` — reusable progress bar
- `frontend/src/composables/useDateRangePicker.ts` — date picker draft-state composable
- `frontend/src/components/editor/nav/NavDateFilter.vue` — filter chip + popup
- `frontend/src/components/editor/nav/NavMapRanges.vue` — map ranges chip + popup
- `frontend/src/components/editor/nav/NavCountryGroup.vue` — expansion item with entries
- `frontend/src/components/editor/nav/NavStepItem.vue` — step entry row
- `frontend/src/components/editor/nav/NavMapItem.vue` — map entry row
- `frontend/src/components/landing/LandingImage.vue` — picture/source/img wrapper
- `frontend/src/utils/refCache.ts` — `makeRefCache` utility (moved from AlbumNav)
- `backend/app/core/async_helpers.py` — `yield_completed` async generator

### Modified
- `frontend/src/queries/keys.ts` — add `createAlbumQuery` factory, `STALE_TIME` stays
- `frontend/src/pages/EditorView.vue` — update query imports
- `frontend/src/pages/PrintView.vue` — update query import
- `frontend/src/components/editor/UserMenu.vue` — replace seg-track/seg-btn with SegmentedControl
- `frontend/src/components/register/TripTimeline.vue` — replace progress bar CSS with ProgressBar component
- `frontend/src/components/album/step/StepMetaPanel.vue` — replace progress bar CSS with ProgressBar component
- `frontend/src/components/editor/AlbumNav.vue` — gut to orchestrator using sub-components
- `frontend/src/pages/LandingView.vue` — replace picture patterns with LandingImage
- `frontend/src/components/album/map/mapSegments.ts` — replace buildFlightArc with turf
- `backend/app/models/user.py` — rename `Provider` to `AuthProvider`
- `backend/app/api/v1/routes/auth.py` — merge endpoints, use `AuthProvider`
- `backend/app/api/v1/deps.py` — add `apply_update` helper
- `backend/app/api/v1/routes/albums.py` — use `apply_update`
- `backend/app/api/v1/routes/users.py` — use `apply_update`
- `backend/app/logic/processing.py` — use `yield_completed`
- `backend/app/logic/layout/builder.py` — use `yield_completed`
- `backend/app/services/open_meteo.py` — use `yield_completed`
- `backend/tests/test_auth.py` — parametrize shared tests
- `backend/tests/test_albums.py` — move helpers to conftest
- `backend/tests/conftest.py` — receive moved helpers

### Deleted
- `frontend/src/queries/useAlbumQuery.ts`
- `frontend/src/queries/useMediaQuery.ts`
- `frontend/src/queries/useStepsQuery.ts`
- `frontend/src/queries/useSegmentsQuery.ts`
- `frontend/src/queries/usePrintBundleQuery.ts`

---

## Task 1: Query Factory

**Files:**
- Create: `frontend/src/queries/queries.ts`
- Modify: `frontend/src/queries/keys.ts`
- Modify: `frontend/src/pages/EditorView.vue:8-11` (imports)
- Modify: `frontend/src/pages/PrintView.vue:3` (import)
- Delete: `frontend/src/queries/useAlbumQuery.ts`, `useMediaQuery.ts`, `useStepsQuery.ts`, `useSegmentsQuery.ts`, `usePrintBundleQuery.ts`

- [ ] **Step 1: Create the factory in `queries.ts`**

```ts
// frontend/src/queries/queries.ts
import { useQuery } from "@pinia/colada";
import { markRaw, type Ref } from "vue";
import { readAlbum, readMedia, readSteps, readSegments, readPrintBundle } from "@/client";
import { queryKeys, STALE_TIME } from "./keys";

type AlbumReadFn<T> = (opts: { path: { aid: string } }) => Promise<{ data: T }>;
type KeyFn = (typeof queryKeys)[keyof typeof queryKeys];

function createAlbumQuery<T>(key: KeyFn, readFn: AlbumReadFn<T>) {
  return (aid: Ref<string | null>) =>
    useQuery({
      key: () => (key as (aid: string | null) => readonly string[])(aid.value),
      query: async () => {
        if (!aid.value) throw new Error("No album selected");
        const { data } = await readFn({ path: { aid: aid.value } });
        return markRaw(data);
      },
      enabled: () => !!aid.value,
      staleTime: STALE_TIME,
    });
}

export const useAlbumQuery = createAlbumQuery(queryKeys.album, readAlbum);
export const useMediaQuery = createAlbumQuery(queryKeys.media, readMedia);
export const useStepsQuery = createAlbumQuery(queryKeys.steps, readSteps);
export const useSegmentsQuery = createAlbumQuery(queryKeys.segments, readSegments);
export const usePrintBundleQuery = createAlbumQuery(queryKeys.printBundle, readPrintBundle);
```

Note: The exact generics for `createAlbumQuery` may need adjustment to satisfy the hey-api generated types. The key constraint is that the factory produces functions with the same `(aid: Ref<string | null>) => UseQueryReturn<T>` signature as the originals. Iterate on the types until `mise run lint:frontend` passes.

- [ ] **Step 2: Update imports in EditorView.vue**

In `frontend/src/pages/EditorView.vue`, replace lines 8-11:

```ts
// Before:
import { useAlbumQuery } from "@/queries/useAlbumQuery";
import { useMediaQuery } from "@/queries/useMediaQuery";
import { useStepsQuery } from "@/queries/useStepsQuery";
import { useSegmentsQuery } from "@/queries/useSegmentsQuery";

// After:
import { useAlbumQuery, useMediaQuery, useStepsQuery, useSegmentsQuery } from "@/queries/queries";
```

- [ ] **Step 3: Update import in PrintView.vue**

In `frontend/src/pages/PrintView.vue`, replace line 3:

```ts
// Before:
import { usePrintBundleQuery } from "@/queries/usePrintBundleQuery";

// After:
import { usePrintBundleQuery } from "@/queries/queries";
```

- [ ] **Step 4: Delete the 5 old files**

```bash
rm frontend/src/queries/useAlbumQuery.ts \
   frontend/src/queries/useMediaQuery.ts \
   frontend/src/queries/useStepsQuery.ts \
   frontend/src/queries/useSegmentsQuery.ts \
   frontend/src/queries/usePrintBundleQuery.ts
```

- [ ] **Step 5: Verify**

Run: `mise run lint:frontend && mise run build`
Expected: PASS — no broken imports, types check.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/queries/ frontend/src/pages/EditorView.vue frontend/src/pages/PrintView.vue
git commit -m "refactor: replace 5 identical query files with createAlbumQuery factory"
```

---

## Task 2: SegmentedControl Component

**Files:**
- Create: `frontend/src/components/ui/SegmentedControl.vue`
- Modify: `frontend/src/components/editor/UserMenu.vue`

- [ ] **Step 1: Create SegmentedControl.vue**

Create `frontend/src/components/ui/SegmentedControl.vue`. The component should:
- Accept props: `modelValue: T`, `options: { label: string; value: T; icon?: string }[]`, `compact?: boolean`
- Emit `update:modelValue`
- Render a `.seg-track` div with a `<button>` per option
- Apply `.active` class when `option.value === modelValue`
- If `option.icon`, render a `<q-icon>` before the label
- If `compact`, add a `compact` class to `.seg-track`

Extract the CSS for `.seg-track` and `.seg-btn` from `UserMenu.vue` lines 334-381 into this component.

- [ ] **Step 2: Replace usages in UserMenu.vue**

In `frontend/src/components/editor/UserMenu.vue`:

1. Import `SegmentedControl` from `@/components/ui/SegmentedControl.vue`
2. Replace the light/dark toggle (template lines ~109-128) with:
   ```vue
   <SegmentedControl
     :model-value="$q.dark.isActive"
     :options="[
       { label: t('settings.light'), value: false, icon: matLightMode },
       { label: t('settings.dark'), value: true, icon: matDarkMode },
     ]"
     @update:model-value="$q.dark.set($event)"
   />
   ```
3. Replace the distance toggle with a `SegmentedControl` using `compact` prop
4. Replace the temperature toggle similarly
5. Delete the `.seg-track` and `.seg-btn` CSS from UserMenu's `<style>` block

- [ ] **Step 3: Verify visually**

Run: `mise run dev:frontend`
Open UserMenu — verify the toggles look and behave identically to before.

- [ ] **Step 4: Lint and build**

Run: `mise run lint:frontend && mise run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ui/SegmentedControl.vue frontend/src/components/editor/UserMenu.vue
git commit -m "refactor: extract SegmentedControl component from UserMenu"
```

---

## Task 3: ProgressBar Component

**Files:**
- Create: `frontend/src/components/ui/ProgressBar.vue`
- Modify: `frontend/src/components/register/TripTimeline.vue`
- Modify: `frontend/src/components/album/step/StepMetaPanel.vue`

- [ ] **Step 1: Create ProgressBar.vue**

Create `frontend/src/components/ui/ProgressBar.vue`. The component should:
- Accept props: `progress: number` (0-1)
- Render `.progress-track` > `.progress-fill` with `transform: scaleX(progress)` on the fill

Extract the CSS from TripTimeline.vue's `.progress-track` / `.progress-fill` styles (lines ~307-318).

```vue
<script lang="ts" setup>
defineProps<{ progress: number }>();
</script>

<template>
  <div class="progress-track">
    <div class="progress-fill" :style="{ transform: `scaleX(${progress})` }" />
  </div>
</template>

<style lang="scss" scoped>
.progress-track {
  height: 0.25rem;
  border-radius: var(--radius-xs);
  background: color-mix(in srgb, var(--q-primary) 12%, transparent);
}

.progress-fill {
  width: 100%;
  height: 100%;
  border-radius: var(--radius-xs);
  background: var(--q-primary);
  transform-origin: left;
  transition: transform var(--duration-slow) cubic-bezier(0.4, 0, 0.2, 1);
}
</style>
```

- [ ] **Step 2: Replace in TripTimeline.vue**

In `frontend/src/components/register/TripTimeline.vue`:
1. Import `ProgressBar`
2. Replace the `.progress-track` / `.progress-fill` template markup with `<ProgressBar :progress="..." />`
3. Delete the `.progress-track` and `.progress-fill` CSS rules

- [ ] **Step 3: Replace in StepMetaPanel.vue**

Same pattern in `frontend/src/components/album/step/StepMetaPanel.vue`.

- [ ] **Step 4: Verify visually**

Run: `mise run dev:frontend`
Check both the TripTimeline (registration flow) and StepMetaPanel (editor) progress bars.

- [ ] **Step 5: Lint and build**

Run: `mise run lint:frontend && mise run build`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ui/ProgressBar.vue \
       frontend/src/components/register/TripTimeline.vue \
       frontend/src/components/album/step/StepMetaPanel.vue
git commit -m "refactor: extract ProgressBar component from TripTimeline and StepMetaPanel"
```

---

## Task 4: AlbumNav Decomposition

This is the largest task. It decomposes `frontend/src/components/editor/AlbumNav.vue` (1,147 lines) into 5 sub-components + 1 composable + 1 utility. Work bottom-up: leaf components first, then containers, then rewire AlbumNav.

**Files:**
- Create: `frontend/src/utils/refCache.ts`
- Create: `frontend/src/composables/useDateRangePicker.ts`
- Create: `frontend/src/components/editor/nav/NavStepItem.vue`
- Create: `frontend/src/components/editor/nav/NavMapItem.vue`
- Create: `frontend/src/components/editor/nav/NavCountryGroup.vue`
- Create: `frontend/src/components/editor/nav/NavDateFilter.vue`
- Create: `frontend/src/components/editor/nav/NavMapRanges.vue`
- Modify: `frontend/src/components/editor/AlbumNav.vue`

- [ ] **Step 1: Extract `makeRefCache` to `utils/refCache.ts`**

Move `makeRefCache` from AlbumNav.vue lines 297-312 to `frontend/src/utils/refCache.ts`. Export it.

```ts
// frontend/src/utils/refCache.ts

/** Stable ref-callback cache: avoids creating new closures on each render while cleaning up on unmount. */
export function makeRefCache<T>() {
  const refs = new Map<string, T>();
  const fns = new Map<string, (el: unknown) => void>();
  function setter(key: string) {
    let fn = fns.get(key);
    if (!fn) {
      fn = (el: unknown) => {
        if (el) { refs.set(key, el as T); }
        else { refs.delete(key); fns.delete(key); }
      };
      fns.set(key, fn);
    }
    return fn;
  }
  return { refs, setter };
}
```

- [ ] **Step 2: Extract `useDateRangePicker` composable**

Create `frontend/src/composables/useDateRangePicker.ts`. This captures the shared draft-state pattern used by both the filter picker (AlbumNav lines 74-109) and the map ranges picker (lines 249-278).

Study both picker patterns in AlbumNav.vue:
- Both have a `draft` ref, an `open` function (copies current model to draft), and a `close` function (parses draft back into `[string, string][]` ranges and calls a mutation callback)
- The parsing logic (QDate → ISO, normalize from/to order) is identical between both

Extract the shared logic into a composable:

```ts
// frontend/src/composables/useDateRangePicker.ts
import { ref, type Ref } from "vue";
import { toIso } from "@/utils/date";
import type { DateRange } from "@/client";

type QDateRange = { from: string; to: string };
type DraftValue = (QDateRange | string)[] | QDateRange | string | null;

/** Parse a QDate draft value into sorted ISO DateRange pairs. */
export function parseDraftRanges(val: DraftValue): DateRange[] {
  if (!val) return [];
  const entries = Array.isArray(val) ? val : [val];
  const ranges = entries.map((e): DateRange => {
    if (typeof e === "string") return [toIso(e), toIso(e)];
    const a = toIso(e.from), b = toIso(e.to);
    return a <= b ? [a, b] : [b, a];
  });
  ranges.sort(([a], [b]) => a.localeCompare(b));
  return ranges;
}

export function useDateRangePicker(toModel: () => DraftValue) {
  const draft = ref<DraftValue>(null);
  const isOpen = ref(false);

  function open() {
    draft.value = toModel() ?? null;
    isOpen.value = true;
  }

  function close(): DraftValue {
    isOpen.value = false;
    return draft.value;
  }

  return { draft, isOpen, open, close };
}
```

- [ ] **Step 3: Create NavStepItem.vue**

Create `frontend/src/components/editor/nav/NavStepItem.vue`. Extract from AlbumNav template lines 566-593 + the relevant CSS (`.nav-item`, `.item-thumb`, `.thumb-img`, `.thumb-empty`, `.item-info`, `.item-name`, `.item-date`, `.step-toggle`).

Props:
- `name: string`, `date: string` (formatted), `thumb: string | null`, `color: string`
- `active: boolean`, `excluded: boolean`

Emits: `click`, `toggle`

- [ ] **Step 4: Create NavMapItem.vue**

Create `frontend/src/components/editor/nav/NavMapItem.vue`. Extract from AlbumNav template lines 519-564 + CSS (`.map-item`, `.map-thumb`, `.map-dates`, `.map-delete`).

This component owns the inline date-editor popup (StepDatePicker + q-popup-proxy). It uses `makeRefCache` from `@/utils/refCache` for the popup/datepicker refs.

Props:
- `dateRange: DateRange`, `rangeIdx: number`, `active: boolean`
- `steps: Step[]`, `colors: Record<string, string>`
- `formatMapRange: (dr: DateRange) => string`

Emits: `click`, `delete`, `date-change: (rangeIdx: number, range: DateRange) => void`

- [ ] **Step 5: Create NavCountryGroup.vue**

Create `frontend/src/components/editor/nav/NavCountryGroup.vue`. Extract the `<q-expansion-item>` from AlbumNav lines 489-595 + CSS (`.group-header`, `.group-avatar`, `.group-flag`, `.group-name`, `.group-dates`, `.country-toggle`).

Props:
- `group: CountryVisit`, `open: boolean`, `activeStepId: number | null`, `activeSectionKey: string | null`
- `excludedSet: Set<number>`, `steps: Step[]`, `colors: Record<string, string>`
- `formatMapRange: (dr: DateRange) => string`

Emits: `toggle-open`, `scroll-to-step: number`, `scroll-to-map: DateRange`, `toggle-step: number`, `toggle-country`, `delete-map: number`, `map-date-change: (rangeIdx: number, range: DateRange) => void`

Uses NavStepItem and NavMapItem internally.

- [ ] **Step 6: Create NavDateFilter.vue**

Create `frontend/src/components/editor/nav/NavDateFilter.vue`. Extract from AlbumNav:
- Script: lines 72-117 (excludedSet, filterDraft, dateRangeModel, onFilterPickerOpen/Close, rangeDisplay, clearFilter)
- Template: lines 416-436 (the filter chip + popup)
- CSS: `.nav-chip`, `.chip-chevron`, `.picker-panel`, `.picker-footer`, `.picker-clear-btn`

Uses `useDateRangePicker` composable.

Props:
- `steps: Step[]`, `excludedSteps: number[]`, `colors: Record<string, string>`

Emits: `update:excluded-steps: number[]`

- [ ] **Step 7: Create NavMapRanges.vue**

Create `frontend/src/components/editor/nav/NavMapRanges.vue`. Extract from AlbumNav:
- Script: lines 249-285 (mapRangesDraft, mapRangesModel, onMapRangesPickerOpen/Close, clearAllMaps, confirmingMapClear)
- Template: lines 438-472 (the map ranges chip + popup + confirm dialog)
- CSS: `.picker-confirm-text`, `.picker-confirm-actions`, `.picker-cancel-btn`, `.picker-remove-btn`

Uses `useDateRangePicker` composable.

Props:
- `steps: Step[]`, `mapsRanges: DateRange[]`, `colors: Record<string, string>`

Emits: `update:maps-ranges: DateRange[]`

- [ ] **Step 8: Rewire AlbumNav.vue**

Rewrite `frontend/src/components/editor/AlbumNav.vue` as an orchestrator:
1. Import all sub-components + `useDateRangePicker` + `makeRefCache` from new locations
2. Remove all code that moved to sub-components
3. Keep: album selector (q-select), `groups` computed, header items, scroll-sync watchers, `openGroupKey` state
4. Template becomes: album selector, `<NavDateFilter>`, `<NavMapRanges>`, header items loop, `<NavCountryGroup v-for>`
5. CSS keeps only: `.album-nav`, `.nav-album-select`, `.album-select-label`, `.nav-controls`, `.nav-list`, `.header-items`, `.header-item`, `.nav-item` (base styles), `@media` queries

The `CountryVisit`, `GroupEntry`, `StepItem` types should move to a shared `nav/types.ts` if needed by multiple sub-components, or stay in AlbumNav if only it computes them.

- [ ] **Step 9: Verify visually**

Run: `mise run dev:frontend`
Test the full AlbumNav:
- Album selector dropdown
- Date filter chip + popup + clearing
- Map ranges chip + popup + confirm clear dialog
- Country group expand/collapse
- Step item click → scrolls to step
- Step visibility toggle
- Map item click → scrolls to map
- Map inline date editor
- Map delete button
- Country-level visibility toggle
- Scroll sync: scrolling the album updates nav highlighting

- [ ] **Step 10: Lint and build**

Run: `mise run lint:frontend && mise run build`
Expected: PASS

- [ ] **Step 11: Commit**

```bash
git add frontend/src/utils/refCache.ts \
       frontend/src/composables/useDateRangePicker.ts \
       frontend/src/components/editor/nav/ \
       frontend/src/components/editor/AlbumNav.vue
git commit -m "refactor: decompose AlbumNav into focused sub-components

Extract NavDateFilter, NavMapRanges, NavCountryGroup, NavStepItem,
NavMapItem. Extract useDateRangePicker composable and makeRefCache
utility. AlbumNav reduced from 1147 to ~250-300 lines."
```

---

## Task 5: LandingImage Component

**Files:**
- Create: `frontend/src/components/landing/LandingImage.vue`
- Modify: `frontend/src/pages/LandingView.vue`

- [ ] **Step 1: Create LandingImage.vue**

Read `frontend/src/pages/LandingView.vue` and identify:
1. The `srcset()` helper function (around line 31-35)
2. All `<picture>` elements that use it (should be 5 occurrences)
3. The exact pattern: `<picture>` > `<source :srcset="srcset(name)" sizes="..." type="image/webp" />` > `<img :src="/landing/${name}-${mode}.jpg" ... />`

Create `frontend/src/components/landing/LandingImage.vue`:

```vue
<script lang="ts" setup>
defineProps<{
  name: string;
  mode: "light" | "dark";
  sizes?: string;
}>();

function srcset(name: string, mode: string) {
  return `(/landing/${name}-${mode}.webp 1x, /landing/${name}-${mode}@2x.webp 2x`;
}
</script>

<template>
  <picture>
    <source :srcset="srcset(name, mode)" :sizes="sizes ?? '320px'" type="image/webp" />
    <img :src="`/landing/${name}-${mode}.jpg`" alt="" />
  </picture>
</template>
```

Note: The exact `srcset` function signature and format must match the original in LandingView.vue. Read the file carefully and replicate it exactly.

- [ ] **Step 2: Replace all usages in LandingView.vue**

In `frontend/src/pages/LandingView.vue`:
1. Import `LandingImage`
2. Replace each `<picture>...</picture>` block with `<LandingImage :name="..." :mode="mode" class="..." />`
3. Delete the `srcset()` helper function
4. Preserve any class attributes on the original `<picture>` or `<img>` — pass them to LandingImage (they'll fall through to the root `<picture>` element)

- [ ] **Step 3: Verify visually**

Run: `mise run dev:frontend`
Check the landing page — all images should render identically.

- [ ] **Step 4: Lint and build**

Run: `mise run lint:frontend && mise run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/landing/LandingImage.vue frontend/src/pages/LandingView.vue
git commit -m "refactor: extract LandingImage component from LandingView"
```

---

## Task 6: Auth Route Consolidation

**Files:**
- Modify: `backend/app/models/user.py:51` — rename `Provider` to `AuthProvider`
- Modify: `backend/app/api/v1/routes/auth.py` — merge endpoints
- Modify: `backend/tests/test_auth.py` — update URLs (now `/{provider}`)

- [ ] **Step 1: Rename Provider to AuthProvider**

In `backend/app/models/user.py`, rename `Provider` to `AuthProvider` on line 51:

```python
# Before:
Provider = Literal["google", "microsoft"]

# After:
AuthProvider = Literal["google", "microsoft"]
```

Then update all references. There should be one in `user.py` (the `OAuthIdentity.provider` field annotation) and imports in `auth.py`.

Run: `mise run lint:backend` to find any missed references.

- [ ] **Step 2: Merge auth endpoints**

In `backend/app/api/v1/routes/auth.py`:

Replace the two endpoints (lines 124-135):

```python
# Before:
@router.post("/google")
async def auth_google(
    body: Credential, request: Request, session: SessionDep
) -> User | None:
    return await _authenticate(body.credential, "google", request, session)


@router.post("/microsoft")
async def auth_microsoft(
    body: Credential, request: Request, session: SessionDep
) -> User | None:
    return await _authenticate(body.credential, "microsoft", request, session)

# After:
@router.post("/{provider}")
async def authenticate(
    provider: AuthProvider, body: Credential, request: Request, session: SessionDep
) -> User | None:
    return await _authenticate(body.credential, provider, request, session)
```

Update the import of `Provider` to `AuthProvider` from `app.models.user`.

- [ ] **Step 3: Run backend tests**

Run: `mise run test:backend`
Expected: PASS — the test URLs (`/api/v1/auth/google`, `/api/v1/auth/microsoft`) still work because FastAPI matches `/{provider}` with the literal path segment.

- [ ] **Step 4: Lint**

Run: `mise run lint:backend`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/user.py backend/app/api/v1/routes/auth.py
git commit -m "refactor: merge auth endpoints into single /{provider} route, rename to AuthProvider"
```

---

## Task 7: Backend Helpers

### 7a: apply_update

**Files:**
- Modify: `backend/app/api/v1/deps.py`
- Modify: `backend/app/api/v1/routes/albums.py`
- Modify: `backend/app/api/v1/routes/users.py`

- [ ] **Step 1: Add `apply_update` to deps.py**

Add to `backend/app/api/v1/deps.py`:

```python
from pydantic import BaseModel
from sqlmodel import SQLModel

async def apply_update[M: SQLModel](
    session: AsyncSession, obj: M, update: BaseModel, *, refresh: bool = True
) -> M:
    """Apply a partial update, commit, and optionally refresh."""
    obj.sqlmodel_update(update.model_dump(exclude_unset=True))
    session.add(obj)
    await session.commit()
    if refresh:
        await session.refresh(obj)
    return obj
```

- [ ] **Step 2: Use in albums.py**

In `backend/app/api/v1/routes/albums.py`, replace the two PATCH patterns:

```python
# update_album (around line 142):
# Before:
    album.sqlmodel_update(update.model_dump(exclude_unset=True))
    session.add(album)
    await session.commit()
    await session.refresh(album)
    return AlbumMeta.model_validate(album)
# After:
    await apply_update(session, album, update)
    return AlbumMeta.model_validate(album)

# update_step (around line 158):
# Before:
    step.sqlmodel_update(update.model_dump(exclude_unset=True))
    session.add(step)
    await session.commit()
    await session.refresh(step)
    return step
# After:
    return await apply_update(session, step, update)
```

Add `apply_update` to the import from `..deps`.

- [ ] **Step 3: Use in users.py**

In `backend/app/api/v1/routes/users.py` (around line 210):

```python
# Before:
    user.sqlmodel_update(update.model_dump(exclude_unset=True))
    session.add(user)
    await session.commit()
    return user
# After:
    return await apply_update(session, user, update, refresh=False)
```

- [ ] **Step 4: Run tests and lint**

Run: `mise run test:backend && mise run lint:backend`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/deps.py backend/app/api/v1/routes/albums.py backend/app/api/v1/routes/users.py
git commit -m "refactor: extract apply_update helper for PATCH routes"
```

### 7b: yield_completed

**Files:**
- Create: `backend/app/core/async_helpers.py`
- Modify: `backend/app/logic/processing.py`
- Modify: `backend/app/logic/layout/builder.py`
- Modify: `backend/app/services/open_meteo.py`

- [ ] **Step 1: Create async_helpers.py**

```python
# backend/app/core/async_helpers.py
import asyncio
from collections.abc import AsyncIterator, Coroutine, Iterable


async def yield_completed[T](coros: Iterable[Coroutine[object, object, T]]) -> AsyncIterator[T]:
    """Yield results from coroutines as each completes (unordered)."""
    for coro in asyncio.as_completed(coros):
        yield await coro
```

- [ ] **Step 2: Replace in processing.py**

In `backend/app/logic/processing.py` (around line 86), find:

```python
for coro in asyncio.as_completed([_one(i, s) for i, s in enumerate(steps)]):
    yield await coro
```

Replace with:

```python
async for result in yield_completed(_one(i, s) for i, s in enumerate(steps)):
    yield result
```

Add import: `from app.core.async_helpers import yield_completed`

- [ ] **Step 3: Replace in builder.py**

In `backend/app/logic/layout/builder.py` (around line 132), find the same `asyncio.as_completed` pattern. Replace similarly with `yield_completed`.

- [ ] **Step 4: Replace in open_meteo.py**

In `backend/app/services/open_meteo.py` (around line 199), replace the same pattern.

- [ ] **Step 5: Run tests and lint**

Run: `mise run test:backend && mise run lint:backend`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/async_helpers.py \
       backend/app/logic/processing.py \
       backend/app/logic/layout/builder.py \
       backend/app/services/open_meteo.py
git commit -m "refactor: extract yield_completed async helper"
```

---

## Task 8: Test Improvements

### 8a: Parametrize Auth Tests

**Files:**
- Modify: `backend/tests/test_auth.py`

- [ ] **Step 1: Parametrize the 3 shared test methods**

In `backend/tests/test_auth.py`, replace `TestAuthGoogle` and `TestAuthMicrosoft` (lines 25-81) with a single parametrized set + a Microsoft-only class:

```python
@pytest.mark.parametrize(
    ("provider", "sub_field", "sub_value"),
    [
        ("google", "google_sub", "google-123"),
        ("microsoft", "microsoft_sub", "microsoft-456"),
    ],
)
class TestAuthProvider:
    async def test_invalid_jwt(self, client: AsyncClient, provider: str, sub_field: str, sub_value: str) -> None:
        with mock_jwt(provider, decode_error=True):
            resp = await client.post(f"/api/v1/auth/{provider}", json={"credential": "bad"})
        assert resp.status_code == 401

    async def test_new_user_returns_null(self, client: AsyncClient, provider: str, sub_field: str, sub_value: str) -> None:
        with mock_jwt(provider):
            resp = await client.post(f"/api/v1/auth/{provider}", json={"credential": "fake"})
        assert resp.status_code == 200
        assert resp.json() is None

    async def test_existing_user_returns_user(
        self, client: AsyncClient, tmp_path: Path, provider: str, sub_field: str, sub_value: str,
    ) -> None:
        await sign_in_and_upload(client, tmp_path / "users", provider=provider)
        await client.post("/api/v1/auth/logout")

        with mock_jwt(provider):
            resp = await client.post(f"/api/v1/auth/{provider}", json={"credential": "fake"})
        assert resp.status_code == 200
        user = resp.json()
        assert user is not None
        assert user[sub_field] == sub_value


class TestAuthMicrosoftSpecific:
    """Tests specific to Microsoft auth (issuer validation, config, name fallback)."""

    async def test_bad_issuer_returns_401(self, client: AsyncClient) -> None:
        bad_iss = {**MICROSOFT_PAYLOAD, "iss": "https://evil.example.com/v2.0"}
        with mock_jwt("microsoft", payload=bad_iss):
            resp = await client.post("/api/v1/auth/microsoft", json={"credential": "fake"})
        assert resp.status_code == 401

    async def test_not_configured_returns_501(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(get_settings(), "VITE_MICROSOFT_CLIENT_ID", "")
        with mock_jwt("microsoft"):
            resp = await client.post("/api/v1/auth/microsoft", json={"credential": "fake"})
        assert resp.status_code == 501

    async def test_falls_back_to_name_when_no_given_name(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        no_given = {k: v for k, v in MICROSOFT_PAYLOAD.items() if k != "given_name"}
        user = await sign_in_and_upload(
            client, tmp_path / "users", provider="microsoft", payload=no_given
        )
        assert user["first_name"] == "Test Microsoft"
```

- [ ] **Step 2: Run tests**

Run: `mise run test:backend`
Expected: PASS — 6 auth provider tests (3 x 2 providers) + 3 Microsoft-specific

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_auth.py
git commit -m "refactor: parametrize shared auth provider tests"
```

### 8b: Consolidate Test Fixtures

**Files:**
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_albums.py`

- [ ] **Step 1: Move helpers to conftest.py**

Move `_insert_album`, `_insert_step`, `_insert_segment` and their supporting constants (`LOCATION`, `WEATHER`, `AID`, `_make_points`) from `backend/tests/test_albums.py` to `backend/tests/conftest.py`.

Keep the functions as plain async helpers (not fixtures) since tests call them with varying arguments. Rename with the leading underscore removed since they're now shared: `insert_album`, `insert_step`, `insert_segment`, `make_points`.

- [ ] **Step 2: Update imports in test_albums.py**

In `backend/tests/test_albums.py`, replace the inline function definitions with imports:

```python
from .conftest import (
    AID,
    LOCATION,
    WEATHER,
    insert_album,
    insert_segment,
    insert_step,
    make_points,
    sign_in_and_upload,
)
```

Update all call sites from `_insert_album` → `insert_album`, etc.

- [ ] **Step 3: Run tests**

Run: `mise run test:backend`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/conftest.py backend/tests/test_albums.py
git commit -m "refactor: move test_albums helpers to shared conftest"
```

---

## Task 9: Flight Arc Package Replacement

**Files:**
- Modify: `frontend/src/components/album/map/mapSegments.ts`
- Modify: `frontend/package.json` (new dependency)

- [ ] **Step 1: Install @turf/bezier-spline**

```bash
cd frontend && bun add @turf/bezier-spline
```

Note: `@turf/helpers` (for `lineString`) is already a dependency.

- [ ] **Step 2: Replace buildFlightArc**

In `frontend/src/components/album/map/mapSegments.ts`, replace `buildFlightArc` (lines 69-99):

```ts
// Before:
function buildFlightArc(
  startLon: number,
  startLat: number,
  endLon: number,
  endLat: number,
  steps = 64,
): [number, number][] {
  // ... 30 lines of manual Bézier math
}

// After:
import bezierSpline from "@turf/bezier-spline";
import { lineString } from "@turf/helpers";

function buildFlightArc(
  startLon: number,
  startLat: number,
  endLon: number,
  endLat: number,
): [number, number][] {
  const dx = endLon - startLon;
  const dy = endLat - startLat;
  const dist = Math.sqrt(dx * dx + dy * dy);
  const offset = dist * 0.2;
  const controlLon = (startLon + endLon) / 2 + (dy / dist) * offset;
  const controlLat = (startLat + endLat) / 2 - (dx / dist) * offset;

  const curved = bezierSpline(
    lineString([[startLon, startLat], [controlLon, controlLat], [endLon, endLat]]),
  );
  return curved.geometry.coordinates as [number, number][];
}
```

The `steps = 64` parameter is dropped — turf's default resolution produces a smooth curve. The control point calculation stays because it defines the perpendicular offset (20% of distance) that gives the arc its visual shape.

- [ ] **Step 3: Verify visually**

Run: `mise run dev:frontend`
Navigate to an album with flight segments. Verify the flight arcs render as smooth curves with the airplane icon positioned correctly at the midpoint.

The curve shape may differ slightly from the old Bézier (Catmull-Rom vs quadratic). This is acceptable per the spec.

- [ ] **Step 4: Lint and build**

Run: `mise run lint:frontend && mise run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/album/map/mapSegments.ts frontend/package.json frontend/bun.lock
git commit -m "refactor: replace custom flight arc Bézier with @turf/bezier-spline"
```

---

## Verification Checklist

After all tasks are complete:

- [ ] `mise run test:backend` — all backend tests pass
- [ ] `mise run test:frontend` — all frontend tests pass
- [ ] `mise run lint` — all linters pass
- [ ] `mise run build` — production build succeeds
- [ ] Visual check: editor sidebar (AlbumNav), user settings (SegmentedControl), registration progress (ProgressBar), landing page images, flight arcs on map pages
