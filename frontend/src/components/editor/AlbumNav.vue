<script lang="ts" setup>
import type {
  AlbumChapter,
  AlbumMedia,
  AlbumMeta,
  DateRange,
  StepRead as Step,
} from "@/client";
import type { GroupEntry, StepItem } from "./nav/types";
import { mediaThumbUrl } from "@/utils/media";
import { parseLocalDate, SHORT_DATE } from "@/utils/date";
import { getCountryColor } from "../album/colors";
import {
  HEADER_KEYS,
  type HeaderKey,
  rangeSectionKey,
  sectionKeyMatchesRange,
} from "../album/albumSections";
import { buildChapterGroups } from "./nav/useAlbumNavGroups";
import { useUserQuery } from "@/queries/useUserQuery";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { useI18n } from "vue-i18n";
import { useActiveSection } from "@/composables/useActiveSection";
import { ref, computed, watch, nextTick } from "vue";
import NavDateFilter from "./nav/NavDateFilter.vue";
import NavMapRanges from "./nav/NavMapRanges.vue";
import NavChapterGroup from "./nav/NavChapterGroup.vue";
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
    album: AlbumMeta;
    media: AlbumMedia[];
    steps: Step[];
    albumIds?: string[];
    hiddenSteps?: number[];
    hiddenHeaders?: HeaderKey[];
    colors?: Record<string, unknown>;
    mapsRanges?: DateRange[];
  }>(),
  {
    albumIds: () => [],
    hiddenSteps: () => [],
    hiddenHeaders: () => [],
    colors: () => ({}),
    mapsRanges: () => [],
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
    countryLabel: countryName(s.location.country_code, s.location.detail),
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

const chaptersForNav = computed<AlbumChapter[]>(() => {
  if (props.album.chapters?.length) return props.album.chapters;
  if (!props.steps.length) return [];
  return [
    {
      id: "chapter-1",
      title: null,
      subtitle: null,
      step_ids: props.steps.map((step) => step.id),
      front_cover_photo: props.album.front_cover_photo,
      back_cover_photo: props.album.back_cover_photo,
    },
  ];
});

const chapterGroups = computed(() =>
  buildChapterGroups({
    steps: props.steps,
    stepItems: stepItems.value,
    mapsRanges: props.mapsRanges,
    chapters: chaptersForNav.value,
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

function formatStepDate(date: Date): string {
  return formatDateRange(date, date, SHORT_DATE);
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
  const groupKey = chapterGroups.value.find((g) =>
    g.entries.some(predicate),
  )?.key;
  if (groupKey && groupKey !== openGroupKey.value) {
    openGroupKey.value = groupKey;
  }
}

watch(activeStepId, (id) => {
  if (id == null) return;
  openGroupFor((e) => e.type === "step" && e.item.id === id);
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
  for (const g of chapterGroups.value) {
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

watch(
  chapterGroups,
  (groups) => {
    if (!openGroupKey.value && groups[0]) openGroupKey.value = groups[0].key;
  },
  { immediate: true },
);
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
      borderless
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
      <div class="nav-filter-row">
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

      <NavChapterGroup
        v-for="group in chapterGroups"
        :key="group.key"
        :group="group"
        :open="openGroupKey === group.key"
        :active-step-id="activeStepId"
        :active-section-key="activeSectionKey"
        :hidden-set="hiddenSet"
        :steps="steps"
        :colors="albumColors"
        :format-map-range="formatMapRange"
        :format-step-date="formatStepDate"
        :section-key-matches-range="sectionKeyMatchesRange"
        :lazy-root="listRef ?? null"
        @toggle-open="
          openGroupKey = openGroupKey === group.key ? null : group.key
        "
        @scroll-to-step="scrollToStep"
        @scroll-to-map="scrollToMap"
        @toggle-step="toggleStep"
        @delete-map="deleteMap"
        @map-date-change="mapDateChange"
      />
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
  margin: var(--gap-sm) var(--gap-md-lg) 0;
  flex-shrink: 0;
  border-radius: var(--radius-xs);
  color: var(--text);
  transition:
    background var(--duration-fast),
    color var(--duration-fast);

  &:hover {
    background: color-mix(in srgb, var(--text) 4%, transparent);
  }

  &:focus-within {
    color: var(--text-bright);
  }

  :deep(.q-field__control) {
    min-height: 2.125rem;
    padding-inline: var(--gap-xs);
  }

  :deep(.q-field__prepend) {
    padding-inline-end: var(--gap-xs);
  }
}

.album-select-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--type-xs);
  font-weight: 600;
}

.nav-controls {
  display: flex;
  flex-direction: column;
  gap: var(--gap-xs);
  padding: var(--gap-sm) var(--gap-md-lg) var(--gap-md);
  flex-shrink: 0;
  border-bottom: 1px solid var(--border-color);
}

.nav-filter-row {
  display: flex;
  gap: var(--gap-xs);
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
  padding-block: var(--gap-xs);
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

@media (prefers-reduced-motion: reduce) {
  .header-item {
    transition: none;
  }
}
</style>
