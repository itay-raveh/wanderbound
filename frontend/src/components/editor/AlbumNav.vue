<script lang="ts" setup>
import type {
  AlbumChapter,
  AlbumMedia,
  AlbumMeta,
  DateRange,
  StepRead as Step,
} from "@/client";
import type {
  ChapterVisit,
  CountryVisit,
  GroupEntry,
  StepItem,
} from "./nav/types";
import { mediaThumbUrl } from "@/utils/media";
import { parseLocalDate, SHORT_DATE } from "@/utils/date";
import { getCountryColor } from "../album/colors";
import {
  HEADER_KEYS,
  type HeaderKey,
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
const openChapterKey = ref<string | null>(null);
const openCountryKey = ref<string | null>(null);

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
  return [];
});

const chapterGroups = computed(() =>
  buildChapterGroups({
    steps: props.steps,
    stepItems: stepItems.value,
    mapsRanges: props.mapsRanges,
    chapters: chaptersForNav.value,
    headerKeys: HEADER_KEYS,
    headerLabel: (key) => t(HEADER_LABELS[key]),
    headerIcon: (key) => HEADER_ICONS[key],
    untitledLabel: (index) => t("chapters.untitled", { number: index + 1 }),
    dateRangeLabel: (first, last) => formatDateRange(first, last, SHORT_DATE),
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

function toggleChapter(group: ChapterVisit) {
  if (openChapterKey.value === group.key) {
    openChapterKey.value = null;
    openCountryKey.value = null;
    return;
  }
  openChapterKey.value = group.key;
  openCountryKey.value = group.countries[0]?.key ?? null;
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

function scrollToMap(key: string) {
  if (scrollToSection(key)) {
    setActive(key);
    return;
  }
  const hikeKey = key.replace("-map-", "-hike-");
  if (hikeKey !== key && scrollToSection(hikeKey)) setActive(hikeKey);
}

function scrollToStep(id: number) {
  scrollTo(id);
  setActive(id);
}

function scrollToHeader(key: string) {
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
// ── Scroll sync ───────────────────────────────────────────────────────

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
  for (const chapter of chapterGroups.value) {
    const country = chapter.countries.find((candidate) =>
      candidate.entries.some(predicate),
    );
    if (!country) continue;
    if (chapter.key !== openChapterKey.value) openChapterKey.value = chapter.key;
    if (country.key !== openCountryKey.value) openCountryKey.value = country.key;
    return;
  }
}

watch(activeStepId, (id) => {
  if (id == null) return;
  openGroupFor((e) => e.type === "step" && e.item.id === id);
  if (programmaticScrolling.value) return;
  scrollNavItemIntoView(`[data-nav-step="${id}"]`);
});

watch(
  chapterGroups,
  (groups) => {
    if (!openChapterKey.value && groups[0]) {
      openChapterKey.value = groups[0].key;
      openCountryKey.value = groups[0].countries[0]?.key ?? null;
    }
  },
  { immediate: true },
);

watch(activeSectionKey, (key) => {
  if (key == null) return;
  for (const chapter of chapterGroups.value) {
    if (chapter.headerItems.some((item) => item.key === key)) {
      if (chapter.key !== openChapterKey.value) openChapterKey.value = chapter.key;
      if (programmaticScrolling.value) return;
      scrollNavItemIntoView(`[data-nav-section="${key}"]`);
      return;
    }
    for (const country of chapter.countries) {
      for (const entry of country.entries) {
        if (entry.type !== "map" || entry.key !== key) continue;
        if (chapter.key !== openChapterKey.value) openChapterKey.value = chapter.key;
        if (country.key !== openCountryKey.value) openCountryKey.value = country.key;
        if (programmaticScrolling.value) return;
        scrollNavItemIntoView(`[data-nav-section="${entry.key}"]`);
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
      <NavChapterGroup
        v-for="group in chapterGroups"
        :key="group.key"
        :group="group"
        :open="openChapterKey === group.key"
        :open-country-key="openCountryKey"
        :active-step-id="activeStepId"
        :active-section-key="activeSectionKey"
        :hidden-set="hiddenSet"
        :hidden-header-set="hiddenHeaderSet"
        :steps="steps"
        :colors="albumColors"
        :format-map-range="formatMapRange"
        :lazy-root="listRef ?? null"
        @toggle-open="toggleChapter(group)"
        @toggle-country-open="
          openCountryKey = openCountryKey === $event ? null : $event
        "
        @scroll-to-step="scrollToStep"
        @scroll-to-map="scrollToMap"
        @scroll-to-header="scrollToHeader"
        @toggle-step="toggleStep"
        @toggle-header="toggleHeader"
        @toggle-country="toggleCountry"
        @delete-map="deleteMap"
        @map-date-change="mapDateChange"
      />
    </div>
  </nav>
</template>

<style lang="scss" scoped>
@use "nav/nav-item";

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
</style>
