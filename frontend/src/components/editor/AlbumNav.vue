<script lang="ts" setup>
import type { DateRange, Step } from "@/client";
import type { CountryVisit, GroupEntry, StepItem } from "./nav/types";
import { mediaThumbUrl } from "@/utils/media";
import { parseLocalDate, SHORT_DATE } from "@/utils/date";
import { getCountryColor } from "../album/colors";
import { HEADER_KEYS, mapInsertionsByStep, rangeSectionKey, sectionKeyMatchesRange } from "../album/albumSections";
import { useUserQuery } from "@/queries/useUserQuery";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { useI18n } from "vue-i18n";
import { useActiveSection } from "@/composables/useActiveSection";
import { ref, computed, watch, nextTick } from "vue";
import NavDateFilter from "./nav/NavDateFilter.vue";
import NavMapRanges from "./nav/NavMapRanges.vue";
import NavCountryGroup from "./nav/NavCountryGroup.vue";
import {
  symOutlinedMap,
  symOutlinedFlightTakeoff,
  symOutlinedMenuBook,
  symOutlinedBarChart,
} from "@quasar/extras/material-symbols-outlined";

const { t } = useI18n();
const { formatDateRange, countryName } = useUserQuery();

const props = withDefaults(
  defineProps<{
    steps: Step[];
    albumIds?: string[];
    excludedSteps?: number[];
    colors?: Record<string, unknown>;
    mapsRanges?: DateRange[];
  }>(),
  { albumIds: () => [], excludedSteps: () => [], colors: () => ({}), mapsRanges: () => [] },
);

const selectedAlbumId = defineModel<string | null>("albumId");

const { activeStepId, activeSectionKey, scrollTo, scrollToSection, scrollBehavior } = useActiveSection();
const albumMutation = useAlbumMutation(() => selectedAlbumId.value ?? "");
const listRef = ref<HTMLElement>();
const openGroupKey = ref<string | null>(null);

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

const excludedSet = computed(() => new Set(props.excludedSteps));
const albumColors = computed(() => (props.colors ?? {}) as Record<string, string>);

const stepItems = computed<StepItem[]>(() =>
  props.steps.map((s) => ({
    id: s.id,
    name: s.name,
    country: s.location.country_code,
    color: getCountryColor(props.colors as Record<string, string>, s.location.country_code),
    date: parseLocalDate(s.datetime),
    thumb: s.cover && selectedAlbumId.value ? mediaThumbUrl(s.cover, selectedAlbumId.value) : null,
    detail: s.location.detail,
  })),
);

const mapInsertions = computed(() => {
  const entries = props.mapsRanges.map((dateRange, rangeIdx) => ({ rangeIdx, dateRange }));
  return mapInsertionsByStep(props.steps, entries);
});

function toMapEntry(m: { rangeIdx: number; dateRange: DateRange }): Extract<GroupEntry, { type: "map" }> {
  return { type: "map", ...m, key: rangeSectionKey("map", m.dateRange) };
}

function computeGroupDateRange(entries: GroupEntry[]): string {
  const steps = entries.filter((e): e is Extract<GroupEntry, { type: "step" }> => e.type === "step");
  const first = steps[0]?.item.date;
  const last = steps.at(-1)?.item.date;
  if (!first || !last) return "";
  return formatDateRange(first, last, SHORT_DATE);
}

const groups = computed<CountryVisit[]>(() => {
  const visits: CountryVisit[] = [];
  for (const item of stepItems.value) {
    const mapEntries = mapInsertions.value.get(item.id)?.map(toMapEntry) ?? [];
    const prev = visits.at(-1);
    if (prev && prev.code === item.country) {
      prev.entries.push(...mapEntries, { type: "step", item });
    } else {
      visits.push({
        key: `${item.country}-${visits.length}`,
        code: item.country,
        name: countryName(item.country, item.detail),
        color: item.color,
        entries: [...mapEntries, { type: "step", item }],
        dateRange: "",
      });
    }
  }
  for (const v of visits) v.dateRange = computeGroupDateRange(v.entries);
  return visits;
});

function formatMapRange(dr: DateRange): string {
  return formatDateRange(parseLocalDate(dr[0]), parseLocalDate(dr[1]), SHORT_DATE);
}

// ── Mutations ─────────────────────────────────────────────────────────

function onExcludedStepsChange(ids: number[]) {
  albumMutation.mutate({ excluded_steps: ids });
}

function onMapsRangesChange(ranges: DateRange[]) {
  albumMutation.mutate({ maps_ranges: ranges });
}

function toggleStep(stepId: number) {
  const excluded = [...props.excludedSteps];
  const idx = excluded.indexOf(stepId);
  if (idx >= 0) excluded.splice(idx, 1);
  else excluded.push(stepId);
  albumMutation.mutate({ excluded_steps: excluded });
}

function countryStepIds(group: CountryVisit): number[] {
  return group.entries
    .filter((e): e is Extract<GroupEntry, { type: "step" }> => e.type === "step")
    .map((e) => e.item.id);
}

function toggleCountry(group: CountryVisit) {
  const stepIds = countryStepIds(group);
  const allExcluded = stepIds.every((id) => excludedSet.value.has(id));
  if (allExcluded) {
    const toRemove = new Set(stepIds);
    albumMutation.mutate({ excluded_steps: props.excludedSteps.filter((id) => !toRemove.has(id)) });
  } else {
    albumMutation.mutate({ excluded_steps: [...new Set([...props.excludedSteps, ...stepIds])] });
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
  if (!scrollToSection(rangeSectionKey("map", dateRange))) {
    scrollToSection(rangeSectionKey("hike", dateRange));
  }
}

// ── Header nav items ──────────────────────────────────────────────────

const HEADER_ICONS: Record<string, string> = {
  "cover-front": symOutlinedMenuBook,
  "cover-back": symOutlinedMenuBook,
  "overview": symOutlinedBarChart,
  "full-map": symOutlinedMap,
};
const HEADER_LABELS: Record<string, string> = {
  "cover-front": "nav.cover",
  "cover-back": "album.backCover",
  "overview": "inspector.overview",
  "full-map": "album.tripRouteMap",
};
const headerNavItems = computed(() =>
  HEADER_KEYS.map((key) => ({ key, icon: HEADER_ICONS[key]!, label: t(HEADER_LABELS[key]!) })),
);

// ── Scroll sync ───────────────────────────────────────────────────────

const HEADER_KEY_SET: ReadonlySet<string> = new Set(HEADER_KEYS);

function scrollNavItemIntoView(selector: string) {
  void nextTick(() => {
    const el = listRef.value?.querySelector(selector);
    (el as HTMLElement | null)?.scrollIntoView({ block: "nearest", behavior: scrollBehavior() });
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
  openGroupFor((e) => e.type === "step" && e.item.id === id);
  scrollNavItemIntoView(`[data-nav-step="${id}"]`);
});

watch(activeSectionKey, (key) => {
  if (key == null) return;
  if (HEADER_KEY_SET.has(key)) {
    scrollNavItemIntoView(`[data-nav-section="${key}"]`);
    return;
  }
  for (const g of groups.value) {
    for (const e of g.entries) {
      if (e.type === "map" && sectionKeyMatchesRange(key, e.dateRange)) {
        if (g.key !== openGroupKey.value) openGroupKey.value = g.key;
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
        <q-icon :name="symOutlinedFlightTakeoff" size="var(--type-md)" class="rtl-flip" />
      </template>
      <template #selected-item="{ opt }">
        <span dir="ltr" class="album-select-label">{{ opt.label }}</span>
      </template>
    </q-select>

    <div v-if="steps.length" class="nav-controls">
      <NavDateFilter
        :steps="steps"
        :excluded-steps="excludedSteps"
        :colors="albumColors"
        @update:excluded-steps="onExcludedStepsChange"
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
        <button
          v-for="item in headerNavItems"
          :key="item.key"
          type="button"
          :data-nav-section="item.key"
          :class="['nav-item', 'header-item', { visible: activeSectionKey === item.key }]"
          @click="scrollToSection(item.key)"
        >
          <q-icon :name="item.icon" size="var(--type-sm)" />
          <span>{{ item.label }}</span>
        </button>
      </div>

      <NavCountryGroup
        v-for="group in groups"
        :key="group.key"
        :group="group"
        :open="openGroupKey === group.key"
        :active-step-id="activeStepId"
        :active-section-key="activeSectionKey"
        :excluded-set="excludedSet"
        :steps="steps"
        :colors="albumColors"
        :format-map-range="formatMapRange"
        @toggle-open="openGroupKey = openGroupKey === group.key ? null : group.key"
        @scroll-to-step="scrollTo"
        @scroll-to-map="scrollToMap"
        @toggle-step="toggleStep"
        @toggle-country="toggleCountry(group)"
        @delete-map="deleteMap"
        @map-date-change="mapDateChange"
      />
    </div>
  </nav>
</template>

<style lang="scss" scoped>
.album-nav {
  --opacity-excluded: 0.45;
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
  border-bottom: 0.0625rem solid var(--border-color);
  padding-bottom: var(--gap-sm);
  margin-bottom: var(--gap-sm);
}

.nav-item {
  appearance: none;
  background: none;
  font: inherit;
  color: inherit;
  text-align: inherit;
  cursor: pointer;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  gap: var(--gap-sm-md);
  width: 100%;
  padding-block: var(--gap-md);
  padding-inline: 2rem var(--gap-md-lg);
  border: none;
  border-inline-start: 0.1875rem solid transparent;
  transition: background var(--duration-fast), border-color var(--duration-fast);

  &:hover {
    background: color-mix(in srgb, var(--text) 6%, transparent);
  }

  &:active {
    background: color-mix(in srgb, var(--text) 10%, transparent);
  }

  &.visible {
    background: color-mix(in srgb, var(--q-primary) 12%, transparent);
    border-inline-start-color: var(--q-primary);

    &:hover {
      background: color-mix(in srgb, var(--q-primary) 18%, transparent);
    }

    &:active {
      background: color-mix(in srgb, var(--q-primary) 24%, transparent);
    }
  }

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: -0.125rem;
  }
}

// Extends .nav-item (added as a class in the template) with compact overrides.
.header-item {
  gap: var(--gap-sm);
  padding: var(--gap-sm) var(--gap-md-lg);
  font-size: var(--type-xs);
  font-weight: 600;
  color: var(--text-muted);

  &:hover {
    color: var(--text-bright);
  }

  &.visible {
    color: var(--q-primary);
  }
}

@media (prefers-reduced-motion: reduce) {
  .header-item,
  .nav-item {
    transition: none;
  }
}
</style>
