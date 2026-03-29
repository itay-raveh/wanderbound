<script lang="ts" setup>
import type { DateRange, Step } from "@/client";
import { flagUrl, mediaThumbUrl } from "@/utils/media";
import { isoDate, parseLocalDate, parseYMD, toQDate, ymdToIso, SHORT_DATE } from "@/utils/date";
import { getCountryColor } from "../album/colors";
import { mapInsertionsByStep, rangeSectionKey, sectionKeyMatchesRange } from "../album/albumSections";
import { useUserQuery } from "@/queries/useUserQuery";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import StepDatePicker from "@/components/editor/StepDatePicker.vue";
import { useI18n } from "vue-i18n";
import { useStepScrollSpy } from "@/composables/useStepScrollSpy";
import { ref, computed, watch, nextTick } from "vue";
import {
  symOutlinedSearch,
  symOutlinedMap,
  symOutlinedClose,
  symOutlinedCalendarMonth,
  symOutlinedMenuBook,
} from "@quasar/extras/material-symbols-outlined";

const { t } = useI18n();
const { formatDate, formatDateRange, countryName } = useUserQuery();

const props = withDefaults(
  defineProps<{
    steps: Step[];
    albumId: string;
    colors?: Record<string, unknown>;
    mapsRanges?: DateRange[];
  }>(),
  { colors: () => ({}), mapsRanges: () => [] },
);

const { visibleStepId, visibleSectionKey, scrollTo, scrollToSection, scrollBehavior } = useStepScrollSpy();
const albumMutation = useAlbumMutation(() => props.albumId);
const listRef = ref<HTMLElement>();
const query = ref("");
const openGroupKey = ref<string | null>(null);
const addingMap = ref(false);

interface StepItem {
  id: number;
  name: string;
  country: string;
  color: string;
  date: Date;
  thumb: string | null;
  detail: string;
}

const stepItems = computed<StepItem[]>(() =>
  props.steps.map((s) => ({
    id: s.id,
    name: s.name,
    country: s.location.country_code,
    color: getCountryColor(props.colors as Record<string, string>, s.location.country_code),
    date: parseLocalDate(s.datetime),
    thumb: s.cover ? mediaThumbUrl(s.cover, props.albumId) : null,
    detail: s.location.detail,
  })),
);

const filteredItems = computed<StepItem[]>(() => {
  const q = query.value.toLocaleLowerCase().trim();
  return q ? stepItems.value.filter((s) => s.name.toLocaleLowerCase().includes(q)) : stepItems.value;
});

const mapInsertions = computed(() => {
  const entries = props.mapsRanges.map((dateRange, rangeIdx) => ({ rangeIdx, dateRange }));
  return mapInsertionsByStep(props.steps, entries);
});

type GroupEntry =
  | { type: "step"; item: StepItem }
  | { type: "map"; rangeIdx: number; dateRange: DateRange; key: string };

interface CountryVisit {
  key: string;
  code: string;
  name: string;
  color: string;
  entries: GroupEntry[];
  dateRange: string;
}

const showMaps = computed(() => !query.value.trim());

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
  for (const item of filteredItems.value) {
    const maps = showMaps.value ? mapInsertions.value.get(item.id) : undefined;
    const mapEntries = maps?.map(toMapEntry) ?? [];
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

function onStepClick(item: StepItem) {
  if (addingMap.value) {
    addMapBefore(item.id);
  } else {
    scrollTo(item.id);
  }
}

function addMapBefore(stepId: number) {
  const step = props.steps.find((s) => s.id === stepId);
  if (!step) return;
  const sd = isoDate(step.datetime);
  const ranges: DateRange[] = [...props.mapsRanges, [sd, sd]];
  ranges.sort(([a], [b]) => a.localeCompare(b));
  albumMutation.mutate({ maps_ranges: ranges });
  addingMap.value = false;
}

function deleteMap(rangeIdx: number) {
  const ranges = [...props.mapsRanges];
  ranges.splice(rangeIdx, 1);
  albumMutation.mutate({ maps_ranges: ranges });
}

function scrollToMap(dateRange: DateRange) {
  if (!scrollToSection(rangeSectionKey("map", dateRange))) {
    scrollToSection(rangeSectionKey("hike", dateRange));
  }
}

type YMD = ReturnType<typeof parseYMD>;
type DatePickerExpose = { setEditingRange: (r: YMD) => void };
type PopupExpose = { hide: () => void };

/** Stable ref-callback cache: avoids creating new closures on each render while cleaning up on unmount. */
function makeRefCache<T>() {
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

const { refs: datePickerRefs, setter: setDatePickerRef } = makeRefCache<DatePickerExpose>();
const { refs: popupProxyRefs, setter: setPopupRef } = makeRefCache<PopupExpose>();

function endDateOptions(dr: DateRange) {
  const min = toQDate(dr[0]);
  return (qdate: string) => qdate >= min;
}

async function onMapDateShow(entry: Extract<GroupEntry, { type: "map" }>) {
  await nextTick();
  datePickerRefs.get(entry.key)?.setEditingRange(parseYMD(entry.dateRange[0]));
}

function onMapDateEnd(key: string, rangeIdx: number, range: { from: YMD; to: YMD }) {
  const ranges = [...props.mapsRanges] as DateRange[];
  const existing = ranges[rangeIdx];
  if (existing) {
    ranges[rangeIdx] = [existing[0], ymdToIso(range.to)];
    albumMutation.mutate({ maps_ranges: ranges });
  }
  popupProxyRefs.get(key)?.hide();
}

watch(query, () => {
  openGroupKey.value = null;
  addingMap.value = false;
});

function openGroupFor(predicate: (e: GroupEntry) => boolean) {
  const groupKey = groups.value.find((g) => g.entries.some(predicate))?.key;
  if (groupKey && groupKey !== openGroupKey.value) {
    openGroupKey.value = groupKey;
  }
}

function scrollNavItemIntoView(selector: string) {
  void nextTick(() => {
    const el = listRef.value?.querySelector(selector);
    (el as HTMLElement | null)?.scrollIntoView({ block: "nearest", behavior: scrollBehavior() });
  });
}

watch(visibleStepId, (id) => {
  if (id == null) return;
  openGroupFor((e) => e.type === "step" && e.item.id === id);
  scrollNavItemIntoView(`[data-nav-step="${id}"]`);
});

watch(visibleSectionKey, (key) => {
  if (key == null) return;
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
  <nav class="album-nav" :aria-label="t('nav.steps')" @keydown.escape="addingMap = false">
    <div class="nav-header">
      <span class="header-label text-muted">{{ t("nav.steps") }}</span>
      <button
        v-if="!addingMap"
        type="button"
        class="add-map-btn"
        :aria-label="t('album.addMap')"
        @click="addingMap = true"
      >
        <q-icon :name="symOutlinedMap" size="var(--type-sm)" />
        <q-tooltip>{{ t("album.addMap") }}</q-tooltip>
      </button>
      <button v-else type="button" class="cancel-btn text-faint" @click="addingMap = false">
        {{ t("album.cancel") }}
      </button>
    </div>

    <q-input
      v-model="query"
      dense
      borderless
      clearable
      debounce="200"
      :placeholder="t('nav.search')"
      :aria-label="t('nav.search')"
      class="nav-search"
    >
      <template #prepend>
        <q-icon :name="symOutlinedSearch" size="var(--type-sm)" class="text-faint" />
      </template>
    </q-input>

    <div v-if="addingMap" class="insertion-hint">
      {{ t("nav.clickToPlace") }}
    </div>

    <div ref="listRef" class="nav-list">
      <button
        type="button"
        :class="['nav-item', 'cover-item', { visible: !visibleStepId && !visibleSectionKey }]"
        @click="scrollToSection('cover-front')"
      >
        <div class="item-thumb cover-thumb">
          <q-icon :name="symOutlinedMenuBook" size="var(--type-md)" />
        </div>
        <div class="item-info">
          <span class="item-name">{{ t("nav.cover") }}</span>
        </div>
      </button>

      <q-expansion-item
        v-for="group in groups"
        :key="group.key"
        :model-value="openGroupKey === group.key"
        dense
        header-class="group-header"
        expand-icon-class="text-faint"
        :style="{ '--country-color': group.color }"
        @update:model-value="openGroupKey = $event ? group.key : null"
      >
        <template #header>
          <q-item-section avatar class="group-avatar">
            <img :src="flagUrl(group.code)" alt="" width="14" height="10" class="group-flag" />
          </q-item-section>
          <q-item-section class="group-name">{{ group.name }}</q-item-section>
          <q-item-section side class="group-dates text-muted">
            {{ group.dateRange }}
          </q-item-section>
        </template>

        <template v-for="entry in group.entries" :key="entry.type === 'step' ? entry.item.id : entry.key">
          <div
            v-if="entry.type === 'map'"
            role="button"
            :data-nav-section="entry.key"
            :class="['nav-item', 'map-item', { visible: sectionKeyMatchesRange(visibleSectionKey, entry.dateRange) }]"
            tabindex="0"
            :aria-label="`${t('nav.map')}: ${formatMapRange(entry.dateRange)}`"
            @click="scrollToMap(entry.dateRange)"
            @keydown.enter="scrollToMap(entry.dateRange)"
            @keydown.space.prevent="scrollToMap(entry.dateRange)"
          >
            <div class="item-thumb map-thumb">
              <q-icon :name="symOutlinedMap" size="var(--type-md)" />
            </div>
            <div class="item-info">
              <span class="item-name">{{ t("nav.map") }}</span>
              <button type="button" class="map-dates" aria-haspopup="dialog" @click.stop>
                <q-icon :name="symOutlinedCalendarMonth" size="var(--type-2xs)" />
                {{ formatMapRange(entry.dateRange) }}
                <q-popup-proxy
                  :ref="setPopupRef(entry.key)"
                  transition-show="scale"
                  transition-hide="scale"
                  @before-show="() => onMapDateShow(entry as Extract<GroupEntry, { type: 'map' }>)"
                >
                  <StepDatePicker
                    :ref="setDatePickerRef(entry.key)"
                    :model-value="{ from: toQDate(entry.dateRange[0]), to: toQDate(entry.dateRange[1]) }"
                    :steps="steps"
                    :colors="(colors as Record<string, string>)"
                    range
                    :options="endDateOptions(entry.dateRange)"
                    @range-end="(range: { from: YMD; to: YMD }) => onMapDateEnd(entry.key, entry.rangeIdx, range)"
                  />
                </q-popup-proxy>
              </button>
            </div>
            <button
              type="button"
              class="map-delete"
              :aria-label="t('album.removeMap')"
              @click.stop="deleteMap(entry.rangeIdx)"
            >
              <q-icon :name="symOutlinedClose" size="var(--type-2xs)" />
              <q-tooltip>{{ t("album.removeMap") }}</q-tooltip>
            </button>
          </div>

          <button
            v-else
            type="button"
            :data-nav-step="entry.item.id"
            :class="['nav-item', { visible: visibleStepId === entry.item.id, inserting: addingMap }]"
            :aria-current="visibleStepId === entry.item.id ? 'step' : undefined"
            @click="onStepClick(entry.item)"
          >
            <div class="item-thumb">
              <img v-if="entry.item.thumb" :src="entry.item.thumb" alt="" width="36" height="28" class="thumb-img" loading="lazy" />
              <div v-else class="thumb-empty" :style="{ background: entry.item.color }" />
            </div>
            <div class="item-info">
              <span class="item-name">{{ entry.item.name }}</span>
              <span class="item-date text-muted">{{ formatDate(entry.item.date, SHORT_DATE) }}</span>
            </div>
          </button>
        </template>
      </q-expansion-item>
      <p v-if="!groups.length && query" class="nav-empty text-faint">
        {{ t("nav.noResults") }}
      </p>
    </div>
  </nav>
</template>

<style lang="scss" scoped>
.album-nav {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-secondary);
}

.nav-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--gap-md) var(--gap-md-lg);
  flex-shrink: 0;
}

.header-label {
  font-size: var(--type-xs);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
}

.add-map-btn {
  appearance: none;
  background: none;
  border: none;
  color: var(--text-faint);
  cursor: pointer;
  padding: var(--gap-sm);
  border-radius: var(--radius-sm);
  transition: color var(--duration-fast), background var(--duration-fast);

  &:hover {
    color: var(--q-primary);
    background: color-mix(in srgb, var(--q-primary) 10%, transparent);
  }

  &:focus-visible {
    outline: 2px solid var(--q-primary);
    outline-offset: 1px;
  }
}

.cancel-btn {
  appearance: none;
  background: none;
  border: none;
  cursor: pointer;
  font: inherit;
  font-size: var(--type-2xs);
  padding: var(--gap-sm) var(--gap-sm-md);
  border-radius: var(--radius-sm);
  transition: color var(--duration-fast);

  &:hover {
    color: var(--text);
  }

  &:focus-visible {
    outline: 2px solid var(--q-primary);
    outline-offset: 1px;
  }
}

.nav-search {
  margin: 0 var(--gap-md-lg) var(--gap-md);
  flex-shrink: 0;
  font-size: var(--type-2xs);
}

.insertion-hint {
  font-size: var(--type-2xs);
  color: var(--q-primary);
  padding: 0 var(--gap-md-lg) var(--gap-md);
  flex-shrink: 0;
}

.nav-list {
  flex: 1;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--border-color) transparent;

  &::-webkit-scrollbar {
    width: 4px;
  }

  &::-webkit-scrollbar-thumb {
    background: var(--border-color);
    border-radius: var(--radius-xs);
  }
}

.group-header {
  min-height: 2.75rem;
  padding: var(--gap-sm) var(--gap-md-lg);
  border-top: 1px solid var(--border-color);
  transition: background var(--duration-fast);

  .q-expansion-item:first-child & {
    border-top: none;
  }

  .q-expansion-item--expanded & {
    background: color-mix(in srgb, var(--country-color) 15%, transparent);
  }
}

.group-avatar {
  min-width: unset;
  padding-inline-end: var(--gap-sm);
}

.group-flag {
  width: 0.875rem;
  height: 0.625rem;
  border-radius: var(--radius-xs);
}

.group-name {
  font-size: var(--type-2xs);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  color: var(--text-muted);
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.group-dates {
  font-size: var(--type-3xs);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
  flex-shrink: 1 !important;
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
  border-inline-start: 3px solid transparent;
  transition: background var(--duration-fast), border-color var(--duration-fast);

  &:hover {
    background: color-mix(in srgb, var(--text) 6%, transparent);
  }

  &:active {
    background: color-mix(in srgb, var(--text) 10%, transparent);
  }

  &.visible {
    background: color-mix(in srgb, var(--country-color) 18%, transparent);
    border-inline-start-color: var(--country-color);

    &:hover {
      background: color-mix(in srgb, var(--country-color) 24%, transparent);
    }

    &:active {
      background: color-mix(in srgb, var(--country-color) 28%, transparent);
    }
  }

  &.inserting:hover {
    background: color-mix(in srgb, var(--q-primary) 12%, transparent);
    border-inline-start-color: var(--q-primary);
  }

  &:focus-visible {
    outline: 2px solid var(--q-primary);
    outline-offset: -2px;
  }
}

.cover-item {
  border-top: none;
  margin-bottom: var(--gap-sm);
  border-bottom: 1px solid var(--border-color);

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
}

.cover-thumb {
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--text) 8%, transparent);
  color: var(--text-muted);

  .cover-item.visible & {
    color: var(--q-primary);
    background: color-mix(in srgb, var(--q-primary) 12%, transparent);
  }
}

.map-item {
  .item-name {
    color: var(--q-primary);
  }
}

.map-dates {
  appearance: none;
  background: none;
  border: none;
  font: inherit;
  display: inline-flex;
  align-items: center;
  gap: var(--gap-xs);
  font-size: var(--type-3xs);
  color: var(--text-muted);
  cursor: pointer;
  padding: var(--gap-xs);
  border-radius: var(--radius-xs);
  border-bottom: 1px dashed color-mix(in srgb, var(--text-muted) 50%, transparent);
  transition: background var(--duration-fast), color var(--duration-fast), border-color var(--duration-fast);

  &:hover {
    color: var(--q-primary);
    background: color-mix(in srgb, var(--q-primary) 10%, transparent);
    border-bottom-color: var(--q-primary);
    border-bottom-style: solid;
  }

  &:focus-visible {
    outline: 2px solid var(--q-primary);
    outline-offset: 1px;
  }
}

.map-thumb {
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--q-primary) 12%, transparent);
  color: var(--q-primary);
}

.map-delete {
  appearance: none;
  background: none;
  border: none;
  cursor: pointer;
  flex-shrink: 0;
  opacity: 0;
  padding: var(--gap-sm-md);
  border-radius: var(--radius-xs);
  color: var(--text-faint);
  transition: opacity var(--duration-fast), color var(--duration-fast);

  .nav-item:hover & {
    opacity: 1;
  }

  &:hover {
    color: var(--text) !important;
  }

  &:focus-visible {
    opacity: 1;
    outline: 2px solid var(--q-primary);
    outline-offset: 1px;
  }
}

.item-thumb {
  width: 2.25rem;
  height: 1.75rem;
  flex-shrink: 0;
  border-radius: var(--radius-xs);
  overflow: hidden;
}

.thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb-empty {
  width: 100%;
  height: 100%;
  opacity: 0.25;
}

.item-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--gap-xs);
}

.item-name {
  font-size: var(--type-2xs);
  font-weight: 600;
  color: var(--text-bright);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-date {
  font-size: var(--type-3xs);
}

.nav-empty {
  margin: 0;
  padding: var(--gap-lg) var(--gap-md-lg);
  font-size: var(--type-2xs);
  text-align: center;
}

@media (hover: none) {
  .map-delete {
    opacity: 1;
  }
}

@media (pointer: coarse) {
  .add-map-btn {
    padding: var(--gap-md-lg);
  }

  .cancel-btn {
    padding: var(--gap-md) var(--gap-md-lg);
  }

  .map-dates {
    padding: var(--gap-sm-md) var(--gap-md);
  }
}

@media (prefers-reduced-motion: reduce) {
  .nav-item,
  .group-header,
  .add-map-btn,
  .map-dates,
  .map-delete,
  .cancel-btn {
    transition: none;
  }
}
</style>
