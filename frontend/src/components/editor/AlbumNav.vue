<script lang="ts" setup>
import type { Step } from "@/client";
import { flagUrl, mediaThumbUrl } from "@/utils/media";
import { parseLocalDate, SHORT_DATE } from "@/utils/date";
import { getCountryColor } from "../album/colors";
import { useUserQuery } from "@/queries/useUserQuery";
import { useI18n } from "vue-i18n";
import { useStepScrollSpy } from "@/composables/useStepScrollSpy";
import { ref, computed, watch, nextTick } from "vue";
import { symOutlinedSearch } from "@quasar/extras/material-symbols-outlined";

const { t } = useI18n();
const { formatDate, formatDateRange, countryName } = useUserQuery();

const props = withDefaults(
  defineProps<{
    steps: Step[];
    albumId: string;
    colors?: Record<string, unknown>;
  }>(),
  { colors: () => ({}) },
);

const { visibleStepId, scrollTo } = useStepScrollSpy();
const listRef = ref<HTMLElement>();
const query = ref("");
const openGroupKey = ref<string | null>(null);

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

interface CountryVisit {
  key: string;
  code: string;
  name: string;
  color: string;
  items: StepItem[];
}

const filteredItems = computed<StepItem[]>(() => {
  const q = query.value.toLocaleLowerCase().trim();
  return q ? stepItems.value.filter((s) => s.name.toLocaleLowerCase().includes(q)) : stepItems.value;
});

const groups = computed<CountryVisit[]>(() => {
  const visits: CountryVisit[] = [];
  for (const item of filteredItems.value) {
    const prev = visits.at(-1);
    if (prev && prev.code === item.country) {
      prev.items.push(item);
    } else {
      visits.push({
        key: `${item.country}-${visits.length}`,
        code: item.country,
        name: countryName(item.country, item.detail),
        color: item.color,
        items: [item],
      });
    }
  }
  return visits;
});

function groupDateRange(items: StepItem[]): string {
  const first = items[0]?.date;
  const last = items.at(-1)?.date;
  if (!first || !last) return "";
  return formatDateRange(first, last, SHORT_DATE);
}

watch(query, () => { openGroupKey.value = null; });

watch(visibleStepId, (id) => {
  if (id == null) return;
  const groupKey = groups.value.find((g) => g.items.some((item) => item.id === id))?.key;
  if (groupKey && groupKey !== openGroupKey.value) {
    openGroupKey.value = groupKey;
  }
  void nextTick(() => {
    if (!listRef.value) return;
    const el = listRef.value.querySelector(`[data-nav-step="${id}"]`);
    if (!el) return;
    const listRect = listRef.value.getBoundingClientRect();
    const elRect = (el as HTMLElement).getBoundingClientRect();
    if (elRect.top < listRect.top || elRect.bottom > listRect.bottom) {
      (el as HTMLElement).scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  });
});

</script>

<template>
  <nav class="album-nav" :aria-label="t('nav.steps')">
    <div class="nav-header">
      <span class="header-label text-muted">{{ t("nav.steps") }}</span>
      <span class="header-count text-faint" aria-live="polite">{{ filteredItems.length }}</span>
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

    <div ref="listRef" class="nav-list">
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
            {{ groupDateRange(group.items) }}
          </q-item-section>
        </template>

        <button
          v-for="item in group.items"
          :key="item.id"
          type="button"
          :data-nav-step="item.id"
          :class="['nav-item', { visible: visibleStepId === item.id }]"
          :aria-current="visibleStepId === item.id ? 'step' : undefined"
          @click="scrollTo(item.id)"
        >
          <div class="item-thumb">
            <img v-if="item.thumb" :src="item.thumb" alt="" width="36" height="28" class="thumb-img" loading="lazy" />
            <div v-else class="thumb-empty" :style="{ background: item.color }" />
          </div>
          <div class="item-info">
            <span class="item-name">{{ item.name }}</span>
            <span class="item-date text-muted">{{ formatDate(item.date, SHORT_DATE) }}</span>
          </div>
        </button>
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

.header-count {
  font-size: var(--type-2xs);
}

.nav-search {
  margin: 0 var(--gap-md-lg) var(--gap-md);
  flex-shrink: 0;
  font-size: var(--type-2xs);
}

.nav-list {
  flex: 1;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--border-color) transparent;
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
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.group-dates {
  font-size: var(--type-3xs);
  white-space: nowrap;
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

  &:focus-visible {
    outline: 2px solid var(--q-primary);
    outline-offset: -2px;
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

@media (prefers-reduced-motion: reduce) {
  .nav-item,
  .group-header {
    transition: none;
  }
}
</style>
