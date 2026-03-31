<script lang="ts" setup>
import type { DateRange, Step } from "@/client";
import { flagUrl, mediaThumbUrl } from "@/utils/media";
import { isoDate, inDateRange, datesToRanges, parseLocalDate, parseYMD, toQDate, toIso, ymdToIso, SHORT_DATE } from "@/utils/date";
import { getCountryColor } from "../album/colors";
import { HEADER_KEYS, mapInsertionsByStep, rangeSectionKey, sectionKeyMatchesRange } from "../album/albumSections";
import { useUserQuery } from "@/queries/useUserQuery";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import StepDatePicker from "@/components/editor/StepDatePicker.vue";
import { useI18n } from "vue-i18n";
import { useQuasar } from "quasar";
import { useActiveSection } from "@/composables/useActiveSection";
import { useUndoStack } from "@/composables/useUndoStack";
import { ref, computed, watch, nextTick } from "vue";
import {
  symOutlinedMap,
  symOutlinedClose,
  symOutlinedCalendarMonth,
  symOutlinedKeyboardArrowDown,
  symOutlinedFlightTakeoff,
  symOutlinedMenuBook,
  symOutlinedBarChart,
  symOutlinedVisibility,
  symOutlinedVisibilityOff,
} from "@quasar/extras/material-symbols-outlined";

const { t } = useI18n();
const $q = useQuasar();
const undoStack = useUndoStack();
const { formatDate, formatDateRange, countryName } = useUserQuery();

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

// ── Album selector (moved from toolbar) ──────────────────────────────

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

// ── Shared types ────────────────────────────────────────────────────

type QDateRange = { from: string; to: string };
type PopupExpose = { hide: () => void };

// ── Date range filter (moved from toolbar, writes excluded_steps) ────

const excludedSet = computed(() => new Set(props.excludedSteps));
const albumColors = computed(() => (props.colors ?? {}) as Record<string, string>);
const filterDraft = ref<(QDateRange | string)[] | QDateRange | string | null>(null);
const filterPickerOpen = ref(false);

const dateRangeModel = computed(() => {
  if (!excludedSet.value.size) return undefined;
  const included = props.steps.filter((s) => !excludedSet.value.has(s.id));
  if (!included.length || included.length === props.steps.length) return undefined;
  return datesToRanges(included.map((s) => isoDate(s.datetime)))
    .map(([from, to]) => ({ from: toQDate(from), to: toQDate(to) }));
});

watch(dateRangeModel, (v) => { if (!filterPickerOpen.value) filterDraft.value = v ?? null; });

function onFilterPickerOpen() {
  filterDraft.value = dateRangeModel.value ?? null;
  filterPickerOpen.value = true;
}

function onFilterPickerClose() {
  filterPickerOpen.value = false;
  const val = filterDraft.value;
  if (!val) {
    albumMutation.mutate({ excluded_steps: [] });
    return;
  }
  const entries = Array.isArray(val) ? val : [val];
  const ranges: [string, string][] = entries.map((e) => {
    if (typeof e === "string") return [toIso(e), toIso(e)];
    const a = toIso(e.from), b = toIso(e.to);
    return a <= b ? [a, b] : [b, a];
  });
  const excluded = props.steps
    .filter((s) => !ranges.some((r) => inDateRange(isoDate(s.datetime), r)))
    .map((s) => s.id);
  albumMutation.mutate({ excluded_steps: excluded });
}

const rangeDisplay = computed(() => {
  if (!excludedSet.value.size) return "";
  const included = props.steps.filter((s) => !excludedSet.value.has(s.id));
  if (!included.length || included.length === props.steps.length) return "";
  const dates = included.map((s) => parseLocalDate(s.datetime)).sort((a, b) => a.getTime() - b.getTime());
  return formatDateRange(dates[0]!, dates.at(-1)!, SHORT_DATE);
});

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
    thumb: s.cover && selectedAlbumId.value ? mediaThumbUrl(s.cover, selectedAlbumId.value) : null,
    detail: s.location.detail,
  })),
);

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

function countryAllExcluded(group: CountryVisit): boolean {
  return countryStepIds(group).every((id) => excludedSet.value.has(id));
}

function toggleCountry(group: CountryVisit) {
  const stepIds = countryStepIds(group);
  if (countryAllExcluded(group)) {
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

const filterPopupRef = ref<PopupExpose>();

function showUndoToast(message: string) {
  $q.notify({
    message,
    timeout: 4000,
    actions: [{ label: t("shortcuts.undo"), color: "primary", handler: () => undoStack.undo() }],
  });
}

function clearFilter() {
  filterDraft.value = null;
  filterPopupRef.value?.hide();
  void nextTick(() => showUndoToast(t("nav.filterCleared")));
}

// ── Batch map range picker ──────────────────────────────────────────

const mapRangesDraft = ref<(QDateRange | string)[] | QDateRange | string | null>(null);
const confirmingMapClear = ref(false);

const mapRangesModel = computed(() => {
  if (!props.mapsRanges.length) return null;
  return props.mapsRanges.map(([from, to]) => ({ from: toQDate(from), to: toQDate(to) }));
});

const mapRangesPopupRef = ref<PopupExpose>();

function onMapRangesPickerOpen() {
  mapRangesDraft.value = mapRangesModel.value ?? null;
  confirmingMapClear.value = false;
}

function onMapRangesPickerClose() {
  const val = mapRangesDraft.value;
  if (!val) {
    albumMutation.mutate({ maps_ranges: [] });
    return;
  }
  const entries = Array.isArray(val) ? val : [val];
  const ranges = entries.map((e): DateRange => {
    if (typeof e === "string") return [toIso(e), toIso(e)];
    const a = toIso(e.from), b = toIso(e.to);
    return a <= b ? [a, b] : [b, a];
  });
  ranges.sort(([a], [b]) => a.localeCompare(b));
  albumMutation.mutate({ maps_ranges: ranges });
}

function clearAllMaps() {
  mapRangesDraft.value = null;
  confirmingMapClear.value = false;
  mapRangesPopupRef.value?.hide();
  void nextTick(() => showUndoToast(t("nav.mapsCleared")));
}

function scrollToMap(dateRange: DateRange) {
  if (!scrollToSection(rangeSectionKey("map", dateRange))) {
    scrollToSection(rangeSectionKey("hike", dateRange));
  }
}

type YMD = ReturnType<typeof parseYMD>;
type DatePickerExpose = { setEditingRange: (r: YMD) => void };

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

function openGroupFor(predicate: (e: GroupEntry) => boolean) {
  const groupKey = groups.value.find((g) => g.entries.some(predicate))?.key;
  if (groupKey && groupKey !== openGroupKey.value) {
    openGroupKey.value = groupKey;
  }
}

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

const HEADER_KEY_SET: ReadonlySet<string> = new Set(HEADER_KEYS);

function scrollNavItemIntoView(selector: string) {
  void nextTick(() => {
    const el = listRef.value?.querySelector(selector);
    (el as HTMLElement | null)?.scrollIntoView({ block: "nearest", behavior: scrollBehavior() });
  });
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
      <button type="button" class="nav-chip" :aria-label="t('nav.dateFilter')" aria-haspopup="dialog" @click.stop>
        <q-icon :name="symOutlinedCalendarMonth" size="var(--type-xs)" />
        <span dir="auto">{{ rangeDisplay || t("album.allDates") }}</span>
        <q-icon :name="symOutlinedKeyboardArrowDown" size="var(--type-xs)" class="chip-chevron" />
        <q-popup-proxy ref="filterPopupRef" transition-show="scale" transition-hide="scale" @before-show="onFilterPickerOpen" @before-hide="onFilterPickerClose">
          <div class="picker-panel">
            <StepDatePicker
              v-model="filterDraft"
              :steps="steps"
              :colors="albumColors"
              range
              multiple
            />
            <div v-if="excludedSet.size" class="picker-footer">
              <button type="button" class="picker-clear-btn" @click="clearFilter">
                {{ t("nav.clearFilter") }}
              </button>
            </div>
          </div>
        </q-popup-proxy>
      </button>

      <button type="button" class="nav-chip" :aria-label="t('nav.mapRanges')" aria-haspopup="dialog" @click.stop>
        <q-icon :name="symOutlinedMap" size="var(--type-xs)" />
        <span>{{ t("nav.maps") }}</span>
        <q-icon :name="symOutlinedKeyboardArrowDown" size="var(--type-xs)" class="chip-chevron" />
        <q-popup-proxy ref="mapRangesPopupRef" transition-show="scale" transition-hide="scale" @before-show="onMapRangesPickerOpen" @before-hide="onMapRangesPickerClose">
          <div class="picker-panel">
            <StepDatePicker
              v-model="mapRangesDraft"
              :steps="steps"
              :colors="albumColors"
              range
              multiple
            />
            <div v-if="mapsRanges.length" class="picker-footer">
              <template v-if="!confirmingMapClear">
                <button type="button" class="picker-clear-btn" @click="confirmingMapClear = true">
                  {{ t("nav.clear") }}
                </button>
              </template>
              <template v-else>
                <span class="picker-confirm-text">{{ t("nav.removeAllMaps") }}</span>
                <div class="picker-confirm-actions">
                  <button type="button" class="picker-cancel-btn" @click="confirmingMapClear = false">
                    {{ t("album.cancel") }}
                  </button>
                  <button type="button" class="picker-remove-btn" @click="clearAllMaps">
                    {{ t("nav.remove") }}
                  </button>
                </div>
              </template>
            </div>
          </div>
        </q-popup-proxy>
      </button>
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

      <q-expansion-item
        v-for="group in groups"
        :key="group.key"
        :model-value="openGroupKey === group.key"
        dense
        :header-class="['group-header', { 'group-excluded': countryAllExcluded(group) }]"
        expand-icon-class="text-faint"
        :style="{ '--country-color': group.color }"
        @update:model-value="openGroupKey = $event ? group.key : null"
      >
        <template #header>
          <q-item-section avatar class="group-avatar">
            <img :src="flagUrl(group.code)" alt="" width="14" height="10" class="group-flag" />
          </q-item-section>
          <q-item-section class="group-name" dir="auto">{{ group.name }}</q-item-section>
          <q-item-section side :class="['group-dates', 'text-muted', { 'group-dates-excluded': countryAllExcluded(group) }]">
            <span class="group-dates-text">{{ group.dateRange }}</span>
            <button
              type="button"
              class="country-toggle"
              :aria-label="countryAllExcluded(group) ? t('nav.showAll') : t('nav.hideAll')"
              @click.stop="toggleCountry(group)"
            >
              <q-icon :name="countryAllExcluded(group) ? symOutlinedVisibilityOff : symOutlinedVisibility" size="var(--type-xs)" />
              <q-tooltip>{{ countryAllExcluded(group) ? t("nav.showAll") : t("nav.hideAll") }}</q-tooltip>
            </button>
          </q-item-section>
        </template>

        <template v-for="entry in group.entries" :key="entry.type === 'step' ? entry.item.id : entry.key">
          <div
            v-if="entry.type === 'map'"
            role="button"
            tabindex="0"
            :data-nav-section="entry.key"
            :class="['nav-item', 'map-item', { visible: sectionKeyMatchesRange(activeSectionKey, entry.dateRange) }]"
            :aria-label="`${t('nav.map')}: ${formatMapRange(entry.dateRange)}`"
            @click="scrollToMap(entry.dateRange)"
            @keydown.enter="scrollToMap(entry.dateRange)"
          >
            <div class="item-thumb map-thumb">
              <q-icon :name="symOutlinedMap" size="var(--type-md)" />
            </div>
            <div class="item-info">
              <span class="item-name">{{ t("nav.map") }}</span>
              <button type="button" class="map-dates" aria-haspopup="dialog" @click.stop>
                <q-icon :name="symOutlinedCalendarMonth" size="var(--type-xs)" />
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
              <q-icon :name="symOutlinedClose" size="var(--type-xs)" />
              <q-tooltip>{{ t("album.removeMap") }}</q-tooltip>
            </button>
          </div>

          <div
            v-else
            role="button"
            tabindex="0"
            :data-nav-step="entry.item.id"
            :class="['nav-item', { visible: activeStepId === entry.item.id, excluded: excludedSet.has(entry.item.id) }]"
            :aria-current="activeStepId === entry.item.id ? 'step' : undefined"
            @click="scrollTo(entry.item.id)"
            @keydown.enter="scrollTo(entry.item.id)"
          >
            <div class="item-thumb">
              <img v-if="entry.item.thumb" :src="entry.item.thumb" alt="" width="36" height="28" class="thumb-img" loading="lazy" />
              <div v-else class="thumb-empty" :style="{ background: entry.item.color }" />
            </div>
            <div class="item-info">
              <span class="item-name" dir="auto">{{ entry.item.name }}</span>
              <span class="item-date text-muted">{{ formatDate(entry.item.date, SHORT_DATE) }}</span>
            </div>
            <button
              type="button"
              class="step-toggle"
              :aria-label="excludedSet.has(entry.item.id) ? t('nav.showStep') : t('nav.hideStep')"
              @click.stop="toggleStep(entry.item.id)"
            >
              <q-icon :name="excludedSet.has(entry.item.id) ? symOutlinedVisibilityOff : symOutlinedVisibility" size="var(--type-xs)" />
              <q-tooltip>{{ excludedSet.has(entry.item.id) ? t("nav.showStep") : t("nav.hideStep") }}</q-tooltip>
            </button>
          </div>
        </template>
      </q-expansion-item>
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

.nav-chip {
  appearance: none;
  background: color-mix(in srgb, var(--text) 8%, transparent);
  border: none;
  display: flex;
  align-items: center;
  gap: var(--gap-sm);
  flex: 1;
  font: inherit;
  font-size: var(--type-xs);
  color: var(--text);
  cursor: pointer;
  padding: var(--gap-sm) var(--gap-sm-md);
  border-radius: var(--radius-md);
  white-space: nowrap;
  transition: color var(--duration-fast), background var(--duration-fast);

  &:hover {
    color: var(--q-primary);
    background: color-mix(in srgb, var(--q-primary) 12%, transparent);
  }

  &:active {
    background: color-mix(in srgb, var(--q-primary) 18%, transparent);
  }

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 0.0625rem;
  }
}

.chip-chevron {
  margin-inline-start: auto;
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

.group-header {
  min-height: 2.75rem;
  padding: var(--gap-sm) var(--gap-md-lg);
  border-top: 0.0625rem solid var(--border-color);
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
  transition: opacity var(--duration-fast);
}

.group-name {
  font-size: var(--type-xs);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  color: var(--text-muted);
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: opacity var(--duration-fast);

  .group-excluded & {
    opacity: var(--opacity-excluded);
  }
}

.group-excluded .group-flag {
  opacity: var(--opacity-excluded);
}

.group-header .group-dates {
  display: grid;
  font-size: var(--type-xs);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
  flex-shrink: 1;

  > * {
    grid-area: 1 / 1;
    justify-self: end;
    align-self: center;
  }
}

.group-dates-text {
  transition: opacity var(--duration-fast);

  .group-header:hover &,
  .group-dates-excluded & {
    opacity: 0;
  }
}

.country-toggle {
  appearance: none;
  background: none;
  border: none;
  cursor: pointer;
  padding: var(--gap-sm);
  border-radius: var(--radius-sm);
  color: var(--text-faint);
  opacity: 0;
  transition: opacity var(--duration-fast), color var(--duration-fast), background var(--duration-fast);

  .group-header:hover &,
  .group-dates-excluded & {
    opacity: 1;
  }

  &:hover {
    color: var(--q-primary);
    background: color-mix(in srgb, var(--q-primary) 10%, transparent);
  }

  &:active {
    background: color-mix(in srgb, var(--q-primary) 16%, transparent);
  }

  &:focus-visible {
    opacity: 1;
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 0.0625rem;
  }
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
  padding-inline: 2rem var(--gap-md-lg); // indent aligns with country name inside group header
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
    background: color-mix(in srgb, var(--country-color) 18%, transparent);
    border-inline-start-color: var(--country-color);

    &:hover {
      background: color-mix(in srgb, var(--country-color) 24%, transparent);
    }

    &:active {
      background: color-mix(in srgb, var(--country-color) 28%, transparent);
    }
  }

  &.excluded {
    opacity: var(--opacity-excluded);
  }

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: -0.125rem;
  }
}

.header-items {
  display: flex;
  flex-direction: column;
  border-bottom: 0.0625rem solid var(--border-color);
  padding-bottom: var(--gap-sm);
  margin-bottom: var(--gap-sm);
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
  font-size: var(--type-xs);
  color: var(--text-muted);
  cursor: pointer;
  padding: var(--gap-xs);
  border-radius: var(--radius-xs);
  border-bottom: 0.0625rem dashed color-mix(in srgb, var(--text-muted) 50%, transparent);
  transition: background var(--duration-fast), color var(--duration-fast), border-color var(--duration-fast);

  &:hover {
    color: var(--q-primary);
    background: color-mix(in srgb, var(--q-primary) 10%, transparent);
    border-bottom-color: var(--q-primary);
    border-bottom-style: solid;
  }

  &:active {
    background: color-mix(in srgb, var(--q-primary) 16%, transparent);
  }

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 0.0625rem;
  }
}

.map-thumb {
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--q-primary) 12%, transparent);
  color: var(--q-primary);
}

.map-delete,
.step-toggle {
  appearance: none;
  background: none;
  border: none;
  cursor: pointer;
  flex-shrink: 0;
  padding: var(--gap-sm);
  border-radius: var(--radius-sm);
  color: var(--text-faint);
  transition: opacity var(--duration-fast), color var(--duration-fast), background var(--duration-fast);

  .nav-item:hover & {
    opacity: 1;
  }

  .nav-item &:hover {
    color: var(--q-primary);
    background: color-mix(in srgb, var(--q-primary) 10%, transparent);
  }

  .nav-item &:active {
    background: color-mix(in srgb, var(--q-primary) 16%, transparent);
  }

  &:focus-visible {
    opacity: 1;
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 0.0625rem;
  }
}

.map-delete {
  opacity: 0;
}

.step-toggle {
  opacity: var(--opacity-toggle-idle);

  .nav-item.excluded & {
    opacity: 1;
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
  opacity: var(--opacity-thumb-empty);
}

.item-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--gap-xs);
}

.item-name {
  font-size: var(--type-xs);
  font-weight: 600;
  color: var(--text-bright);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-date {
  font-size: var(--type-xs);
}

.picker-panel {
  display: flex;
  flex-direction: column;
}

.picker-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--gap-sm) var(--gap-md);
  border-top: 0.0625rem solid var(--border-color);
  gap: var(--gap-sm);
}

.picker-clear-btn {
  appearance: none;
  background: none;
  border: none;
  font: inherit;
  font-size: var(--type-xs);
  color: var(--text-muted);
  cursor: pointer;
  padding: var(--gap-xs) var(--gap-sm);
  border-radius: var(--radius-sm);
  transition: color var(--duration-fast), background var(--duration-fast);
  margin-inline-start: auto;

  &:hover {
    color: var(--danger);
    background: color-mix(in srgb, var(--danger) 10%, transparent);
  }

  &:active {
    background: color-mix(in srgb, var(--danger) 16%, transparent);
  }

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 0.0625rem;
  }
}

.picker-confirm-text {
  font-size: var(--type-xs);
  color: var(--text-muted);
}

.picker-confirm-actions {
  display: flex;
  gap: var(--gap-sm);
  margin-inline-start: auto;
}

.picker-cancel-btn,
.picker-remove-btn {
  appearance: none;
  border: none;
  font: inherit;
  font-size: var(--type-xs);
  cursor: pointer;
  padding: var(--gap-xs) var(--gap-sm-md);
  border-radius: var(--radius-sm);
  transition: background var(--duration-fast);

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 0.0625rem;
  }
}

.picker-cancel-btn {
  background: none;
  color: var(--text-muted);

  &:hover {
    background: color-mix(in srgb, var(--text) 8%, transparent);
  }

  &:active {
    background: color-mix(in srgb, var(--text) 14%, transparent);
  }
}

.picker-remove-btn {
  background: var(--danger);
  color: #fff; // white-on-danger — standard for filled destructive buttons

  &:hover {
    background: color-mix(in srgb, var(--danger) 85%, black);
  }

  &:active {
    background: color-mix(in srgb, var(--danger) 75%, black);
  }
}

@media (hover: none) {
  .map-delete,
  .step-toggle,
  .country-toggle {
    opacity: 1;
  }
}

@media (pointer: coarse) {
  .nav-chip {
    padding: var(--gap-sm-md) var(--gap-md);
  }

  .map-dates {
    padding: var(--gap-sm-md) var(--gap-md);
  }

  .step-toggle,
  .country-toggle,
  .map-delete {
    min-width: 2.75rem;
    min-height: 2.75rem;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--gap-md-lg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .header-item,
  .nav-item,
  .group-header,
  .group-flag,
  .group-name,
  .group-dates-text,
  .nav-chip,
  .map-dates,
  .map-delete,
  .step-toggle,
  .country-toggle,
  .picker-clear-btn,
  .picker-cancel-btn,
  .picker-remove-btn {
    transition: none;
  }
}
</style>
