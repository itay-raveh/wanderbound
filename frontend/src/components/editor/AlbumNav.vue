<script lang="ts" setup>
import type { AlbumChapter, DateRange, StepRead as Step } from "@/client";
import type { CountryVisit, GroupEntry, StepItem } from "./nav/types";
import { mediaThumbUrl } from "@/utils/media";
import { parseLocalDate, SHORT_DATE } from "@/utils/date";
import { getCountryColor } from "../album/colors";
import {
  HEADER_KEYS,
  type HeaderKey,
  mapInsertionsByStep,
  rangeSectionKey,
  sectionKeyMatchesRange,
} from "../album/albumSections";
import {
  buildChapterGroups,
  buildCountryVisits,
  entryKey,
} from "./nav/useAlbumNavGroups";
import { useUserQuery } from "@/queries/useUserQuery";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { useI18n } from "vue-i18n";
import { useActiveSection } from "@/composables/useActiveSection";
import { ref, computed, watch, nextTick } from "vue";
import NavDateFilter from "./nav/NavDateFilter.vue";
import NavMapRanges from "./nav/NavMapRanges.vue";
import NavCountryGroup from "./nav/NavCountryGroup.vue";
import NavMapItem from "./nav/NavMapItem.vue";
import NavStepItem from "./nav/NavStepItem.vue";
import {
  symOutlinedMap,
  symOutlinedFlightTakeoff,
  symOutlinedMenuBook,
  symOutlinedBarChart,
  symOutlinedVisibility,
  symOutlinedVisibilityOff,
} from "@quasar/extras/material-symbols-outlined";

const { t } = useI18n();
const { formatDateRange, countryName } = useUserQuery();

const props = withDefaults(
  defineProps<{
    steps: Step[];
    albumIds?: string[];
    hiddenSteps?: number[];
    hiddenHeaders?: HeaderKey[];
    colors?: Record<string, unknown>;
    mapsRanges?: DateRange[];
    chapters?: AlbumChapter[];
  }>(),
  {
    albumIds: () => [],
    hiddenSteps: () => [],
    hiddenHeaders: () => [],
    colors: () => ({}),
    mapsRanges: () => [],
    chapters: () => [],
  },
);

const selectedAlbumId = defineModel<string | null>("albumId");

const {
  activeStepId,
  activeSectionKey,
  setActive,
  scrollTo,
  scrollToSection,
  scrollBehavior,
  programmaticScrolling,
} = useActiveSection();
const albumMutation = useAlbumMutation(() => selectedAlbumId.value ?? "");
const listRef = ref<HTMLElement>();
const openGroupKey = ref<string | null>(null);
const navMode = ref<"countries" | "chapters">("countries");

// ── Album selector ────────────────────────────────────────────────────

const toTitleCase = (str: string) =>
  str
    .replace(/([a-z])-/g, "$1 ")
    .replace(/_\d+$/, "")
    .replace(
      /\w\S*/g,
      (text) => text.charAt(0).toUpperCase() + text.substring(1).toLowerCase(),
    );

const albumOptions = computed(() =>
  props.albumIds.map((value) => ({ label: toTitleCase(value), value })),
);

// ── Derived state ─────────────────────────────────────────────────────

const hiddenSet = computed(() => new Set(props.hiddenSteps));
const hiddenHeaderSet = computed(() => new Set(props.hiddenHeaders));
const albumColors = computed(
  () => (props.colors ?? {}) as Record<string, string>,
);

const stepItems = computed<StepItem[]>(() =>
  props.steps.map((s) => ({
    id: s.id,
    name: s.name,
    country: s.location.country_code,
    color: getCountryColor(
      props.colors as Record<string, string>,
      s.location.country_code,
    ),
    date: parseLocalDate(s.datetime),
    thumb:
      s.cover && selectedAlbumId.value
        ? mediaThumbUrl(s.cover, selectedAlbumId.value)
        : null,
    detail: s.location.detail,
  })),
);

const mapInsertions = computed(() => {
  const entries = props.mapsRanges.map((dateRange, rangeIdx) => ({
    rangeIdx,
    dateRange,
  }));
  return mapInsertionsByStep(props.steps, entries);
});

const groups = computed<CountryVisit[]>(() =>
  buildCountryVisits({
    stepItems: stepItems.value,
    mapInsertions: mapInsertions.value,
    countryName,
    dateRangeLabel: (first, last) => formatDateRange(first, last, SHORT_DATE),
  }),
);

const chapterGroups = computed(() =>
  buildChapterGroups({
    steps: props.steps,
    stepItems: stepItems.value,
    mapsRanges: props.mapsRanges,
    chapters: props.chapters,
    unassignedLabel: t("chapters.unassigned"),
    untitledLabel: (index) => t("chapters.untitled", { number: index + 1 }),
  }),
);

function formatMapRange(dr: DateRange): string {
  return formatDateRange(
    parseLocalDate(dr[0]),
    parseLocalDate(dr[1]),
    SHORT_DATE,
  );
}

// ── Mutations ─────────────────────────────────────────────────────────

function onHiddenStepsChange(ids: number[]) {
  albumMutation.mutate({ hidden_steps: ids });
}

function onMapsRangesChange(ranges: DateRange[]) {
  albumMutation.mutate({ maps_ranges: ranges });
}

function toggleInList<T>(list: readonly T[], item: T): T[] {
  const copy = [...list];
  const idx = copy.indexOf(item);
  if (idx >= 0) copy.splice(idx, 1);
  else copy.push(item);
  return copy;
}

function toggleStep(stepId: number) {
  albumMutation.mutate({
    hidden_steps: toggleInList(props.hiddenSteps, stepId),
  });
}

function toggleHeader(key: HeaderKey) {
  albumMutation.mutate({
    hidden_headers: toggleInList(props.hiddenHeaders, key),
  });
}

function toggleCountry(group: CountryVisit) {
  const { stepIds } = group;
  const allHidden = stepIds.every((id) => hiddenSet.value.has(id));
  if (allHidden) {
    const toRemove = new Set(stepIds);
    albumMutation.mutate({
      hidden_steps: props.hiddenSteps.filter((id) => !toRemove.has(id)),
    });
  } else {
    albumMutation.mutate({
      hidden_steps: [...new Set([...props.hiddenSteps, ...stepIds])],
    });
  }
}

function deleteMap(rangeIdx: number) {
  const ranges = [...props.mapsRanges];
  ranges.splice(rangeIdx, 1);
  albumMutation.mutate({ maps_ranges: ranges });
}

function mapDateChange(rangeIdx: number, range: DateRange) {
  const ranges = [...props.mapsRanges] as DateRange[];
  const existing = ranges[rangeIdx];
  if (existing) {
    ranges[rangeIdx] = [existing[0], range[1]];
    albumMutation.mutate({ maps_ranges: ranges });
  }
}

function scrollToMap(dateRange: DateRange) {
  const mapKey = rangeSectionKey("map", dateRange);
  if (scrollToSection(mapKey)) {
    setActive(mapKey);
    return;
  }
  const hikeKey = rangeSectionKey("hike", dateRange);
  if (scrollToSection(hikeKey)) {
    setActive(hikeKey);
  }
}

function scrollToStep(id: number) {
  scrollTo(id);
  setActive(id);
}

function scrollToHeader(key: HeaderKey) {
  if (scrollToSection(key)) setActive(key);
}

// ── Header nav items ──────────────────────────────────────────────────

const HEADER_ICONS: Record<HeaderKey, string> = {
  "cover-front": symOutlinedMenuBook,
  "cover-back": symOutlinedMenuBook,
  overview: symOutlinedBarChart,
  "full-map": symOutlinedMap,
};
const HEADER_LABELS: Record<HeaderKey, string> = {
  "cover-front": "nav.cover",
  "cover-back": "album.backCover",
  overview: "inspector.overview",
  "full-map": "album.tripRouteMap",
};
const headerNavItems = computed(() =>
  HEADER_KEYS.map((key) => ({
    key,
    icon: HEADER_ICONS[key],
    label: t(HEADER_LABELS[key]),
  })),
);

// ── Scroll sync ───────────────────────────────────────────────────────

const HEADER_KEY_SET: ReadonlySet<string> = new Set(HEADER_KEYS);

function scrollNavItemIntoView(selector: string) {
  void nextTick(() => {
    const el = listRef.value?.querySelector(selector);
    (el as HTMLElement | null)?.scrollIntoView({
      block: "center",
      behavior: scrollBehavior(),
    });
  });
}

function openGroupFor(predicate: (e: GroupEntry) => boolean) {
  const groupKey = groups.value.find((g) => g.entries.some(predicate))?.key;
  if (groupKey && groupKey !== openGroupKey.value) {
    openGroupKey.value = groupKey;
  }
}

watch(activeStepId, (id) => {
  if (id == null) return;
  if (navMode.value === "countries") {
    openGroupFor((e) => e.type === "step" && e.item.id === id);
  } else {
    const group = chapterGroups.value.find((g) => g.stepIds.includes(id));
    if (group) openGroupKey.value = group.key;
  }
  if (programmaticScrolling.value) return;
  scrollNavItemIntoView(`[data-nav-step="${id}"]`);
});

watch(activeSectionKey, (key) => {
  if (key == null) return;
  if (HEADER_KEY_SET.has(key)) {
    if (programmaticScrolling.value) return;
    scrollNavItemIntoView(`[data-nav-section="${key}"]`);
    return;
  }
  const activeGroups =
    navMode.value === "countries" ? groups.value : chapterGroups.value;
  for (const g of activeGroups) {
    for (const e of g.entries) {
      if (e.type === "map" && sectionKeyMatchesRange(key, e.dateRange)) {
        if (g.key !== openGroupKey.value) openGroupKey.value = g.key;
        if (programmaticScrolling.value) return;
        scrollNavItemIntoView(`[data-nav-section="${e.key}"]`);
        return;
      }
    }
  }
});
</script>

<template>
  <nav class="album-nav" :aria-label="t('nav.steps')">
    <q-select
      v-if="albumIds.length"
      v-model="selectedAlbumId"
      :options="albumOptions"
      :aria-label="t('nav.selectAlbum')"
      class="nav-album-select"
      dense
      outlined
      options-dense
      emit-value
      map-options
    >
      <template #prepend>
        <q-icon
          :name="symOutlinedFlightTakeoff"
          size="var(--type-md)"
          class="rtl-flip"
        />
      </template>
      <template #selected-item="{ opt }">
        <span dir="ltr" class="album-select-label">{{ opt.label }}</span>
      </template>
    </q-select>

    <div v-if="steps.length" class="nav-controls">
      <q-btn-toggle
        v-if="chapters.length"
        v-model="navMode"
        class="nav-mode-toggle"
        dense
        no-caps
        unelevated
        toggle-color="primary"
        :options="[
          { label: t('nav.countries'), value: 'countries' },
          { label: t('nav.chapters'), value: 'chapters' },
        ]"
      />
      <NavDateFilter
        :steps="steps"
        :hidden-steps="hiddenSteps"
        :colors="albumColors"
        @update:hidden-steps="onHiddenStepsChange"
      />
      <NavMapRanges
        :steps="steps"
        :maps-ranges="mapsRanges"
        :colors="albumColors"
        @update:maps-ranges="onMapsRangesChange"
      />
    </div>

    <div ref="listRef" class="nav-list">
      <div class="header-items">
        <div
          v-for="item in headerNavItems"
          :key="item.key"
          role="button"
          tabindex="0"
          :data-nav-section="item.key"
          :class="[
            'nav-item',
            'header-item',
            {
              visible: activeSectionKey === item.key,
              'nav-hidden': hiddenHeaderSet.has(item.key),
            },
          ]"
          @click="scrollToHeader(item.key)"
          @keydown.enter="scrollToHeader(item.key)"
        >
          <q-icon :name="item.icon" size="var(--type-sm)" />
          <span>{{ item.label }}</span>
          <button
            type="button"
            class="header-toggle"
            :aria-label="
              hiddenHeaderSet.has(item.key)
                ? t('nav.showStep')
                : t('nav.hideStep')
            "
            @click.stop="toggleHeader(item.key)"
          >
            <q-icon
              :name="
                hiddenHeaderSet.has(item.key)
                  ? symOutlinedVisibilityOff
                  : symOutlinedVisibility
              "
              size="var(--type-xs)"
            />
          </button>
        </div>
      </div>

      <template v-if="navMode === 'countries'">
        <NavCountryGroup
          v-for="group in groups"
          :key="group.key"
          :group="group"
          :open="openGroupKey === group.key"
          :active-step-id="activeStepId"
          :active-section-key="activeSectionKey"
          :hidden-set="hiddenSet"
          :steps="steps"
          :colors="albumColors"
          :format-map-range="formatMapRange"
          :lazy-root="listRef ?? null"
          @toggle-open="
            openGroupKey = openGroupKey === group.key ? null : group.key
          "
          @scroll-to-step="scrollToStep"
          @scroll-to-map="scrollToMap"
          @toggle-step="toggleStep"
          @toggle-country="toggleCountry(group)"
          @delete-map="deleteMap"
          @map-date-change="mapDateChange"
        />
      </template>
      <template v-else>
        <q-expansion-item
          v-for="group in chapterGroups"
          :key="group.key"
          dense
          :data-chapter-group="group.key"
          :model-value="openGroupKey === group.key"
          header-class="chapter-group-header"
          expand-icon-class="text-faint"
          @update:model-value="
            openGroupKey = openGroupKey === group.key ? null : group.key
          "
        >
          <template #header>
            <q-item-section class="chapter-group-name" dir="auto">
              {{ group.name }}
            </q-item-section>
            <q-item-section side class="chapter-count text-muted">
              {{ group.stepIds.length }}
            </q-item-section>
          </template>
          <template v-for="entry in group.entries" :key="entryKey(entry)">
            <NavMapItem
              v-if="entry.type === 'map'"
              :data-nav-section="entry.key"
              :date-range="entry.dateRange"
              :range-idx="entry.rangeIdx"
              :active="
                sectionKeyMatchesRange(activeSectionKey, entry.dateRange)
              "
              :steps="steps"
              :colors="albumColors"
              :format-map-range="formatMapRange"
              @click="scrollToMap(entry.dateRange)"
              @delete="deleteMap(entry.rangeIdx)"
              @date-change="(idx, range) => mapDateChange(idx, range)"
            />
            <NavStepItem
              v-else
              :data-nav-step="entry.item.id"
              :name="entry.item.name"
              :date="
                formatDateRange(entry.item.date, entry.item.date, SHORT_DATE)
              "
              :thumb="entry.item.thumb"
              :color="entry.item.color"
              :active="activeStepId === entry.item.id"
              :hidden="hiddenSet.has(entry.item.id)"
              :lazy-root="listRef ?? null"
              @click="scrollToStep(entry.item.id)"
              @toggle="toggleStep(entry.item.id)"
            />
          </template>
        </q-expansion-item>
      </template>
    </div>
  </nav>
</template>

<style lang="scss" scoped>
@use "nav/nav-item";
@use "nav/nav-toggle" as *;

.album-nav {
  --opacity-hidden: 0.45;
  --opacity-toggle-idle: 0.5;
  --opacity-thumb-empty: 0.25;

  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-secondary);
}

.nav-album-select {
  margin: var(--gap-md) var(--gap-md-lg) 0;
  flex-shrink: 0;
}

.album-select-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nav-controls {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gap-sm);
  padding: var(--gap-sm) var(--gap-md-lg) var(--gap-md);
  flex-shrink: 0;
}

.nav-mode-toggle {
  width: 100%;
}

.nav-list {
  flex: 1;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--border-color) transparent;

  &::-webkit-scrollbar {
    width: 0.25rem;
  }

  &::-webkit-scrollbar-thumb {
    background: var(--border-color);
    border-radius: var(--radius-xs);
  }
}

.header-items {
  display: flex;
  flex-direction: column;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: var(--gap-sm);
  margin-bottom: var(--gap-sm);
}

.header-item {
  gap: var(--gap-sm);
  padding: var(--gap-sm) var(--gap-md-lg);
  font-size: var(--type-xs);
  font-weight: 600;
  color: var(--text-muted);

  > span {
    flex: 1;
  }

  &:hover {
    color: var(--text-bright);
  }

  &.visible {
    color: var(--q-primary);
    background: color-mix(in srgb, var(--q-primary) 12%, transparent);
    border-inline-start-color: var(--q-primary);

    &:hover {
      background: color-mix(in srgb, var(--q-primary) 18%, transparent);
    }

    &:active {
      background: color-mix(in srgb, var(--q-primary) 24%, transparent);
    }
  }
}

.header-toggle {
  @include nav-toggle;

  .header-item:hover & {
    opacity: 1;
  }

  .header-item.nav-hidden & {
    opacity: 1;
  }
}

.chapter-group-header {
  min-height: 2.75rem;
  padding: var(--gap-sm) var(--gap-md-lg);
  border-top: 1px solid var(--border-color);
}

.chapter-group-name {
  min-width: 0;
  color: var(--text-muted);
  font-size: var(--type-xs);
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  text-transform: uppercase;
  white-space: nowrap;
}

.chapter-count {
  font-size: var(--type-xs);
  font-variant-numeric: tabular-nums;
}

@media (prefers-reduced-motion: reduce) {
  .header-item {
    transition: none;
  }
}
</style>
