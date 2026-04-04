<script lang="ts" setup>
import type { AlbumMeta, SegmentOutline, Step } from "@/client";
import { computeOverview } from "@/composables/useOverview";
import { useUserQuery } from "@/queries/useUserQuery";
import { useI18n } from "vue-i18n";
import { computed } from "vue";
import { flagUrl, weatherIconUrl } from "@/utils/media";
import { countryBounds } from "@/utils/countryBounds";
import { parseLocalDate, SHORT_DATE } from "@/utils/date";
import { toOverviewTone, STAT_COLORS } from "../colors";
import { matLandscape, matExplore } from "@quasar/extras/material-icons";
import { toSvgMercator } from "@/utils/geo";
import CountrySilhouette from "../CountrySilhouette.vue";

const props = defineProps<{
  album: AlbumMeta;
  steps: Step[];
  segments: SegmentOutline[];
}>();

const { user, formatDistance, distanceUnit, formatTemp, formatElevation, formatDate, countryName } = useUserQuery();
const { t } = useI18n();

const overview = computed(() =>
  computeOverview(props.steps, props.segments, null, user.value?.living_location ?? null),
);

const tapestryItems = computed(() =>
  overview.value.countries.map((c) => {
    const raw = props.album.colors[c.code];
    const color = typeof raw === "string" ? toOverviewTone(raw) : "var(--q-primary)";
    return { ...c, color };
  }),
);

const combinedViewBox = computed(() => {
  if (props.steps.length === 0) return undefined;

  // Union of all visited countries' mainland bounds — bounds.json already
  // excludes distant overseas territories, so we can safely include them fully.
  let sMinX = Infinity, sMinY = Infinity, sMaxX = -Infinity, sMaxY = -Infinity;
  for (const c of overview.value.countries) {
    const b = countryBounds[c.code.toLowerCase()];
    if (!b) continue;
    sMinX = Math.min(sMinX, b[0]);
    sMinY = Math.min(sMinY, b[1]);
    sMaxX = Math.max(sMaxX, b[0] + b[2]);
    sMaxY = Math.max(sMaxY, b[1] + b[3]);
  }

  // Fallback to step locations if no country bounds matched
  if (!isFinite(sMinX)) {
    for (const step of props.steps) {
      const [x, y] = toSvgMercator(step.location.lon, step.location.lat);
      sMinX = Math.min(sMinX, x); sMinY = Math.min(sMinY, y);
      sMaxX = Math.max(sMaxX, x); sMaxY = Math.max(sMaxY, y);
    }
  }

  const spanX = sMaxX - sMinX || 1;
  const spanY = sMaxY - sMinY || 1;
  const padX = spanX * 0.15;
  const padY = spanY * 0.15;
  return `${sMinX - padX} ${sMinY - padY} ${spanX + padX * 2} ${spanY + padY * 2}`;
});

// ── Fact items (derived from overview extremes) ──────────────

interface FactItem {
  label: string;
  value: string;
  place: string;
  countryCode: string;
  date: string;
  color: string;
  iconUrl?: string;
  iconName?: string;
}

const fmtDate = (s: Step) => formatDate(parseLocalDate(s.datetime), SHORT_DATE);

const stepMeta = (step: Step) => ({
  place: step.name,
  countryCode: step.location.country_code,
  date: fmtDate(step),
});

/** All facts in display order: spatial first, then weather. */
const allFacts = computed<FactItem[]>(() => {
  const o = overview.value;
  const items: FactItem[] = [];

  if (o.furthestFromHome) {
    items.push({
      label: t("overview.furthestFromHome"),
      value: `${formatDistance(o.furthestFromHome.value)} ${distanceUnit.value}`,
      ...stepMeta(o.furthestFromHome.step),
      color: STAT_COLORS.distance,
      iconName: matExplore,
    });
  }

  if (o.highestElevation) {
    items.push({
      label: t("overview.highest"),
      value: formatElevation(o.highestElevation.value),
      ...stepMeta(o.highestElevation.step),
      color: STAT_COLORS.elevation,
      iconName: matLandscape,
    });
  }

  if (o.hottest) {
    items.push({
      label: t("overview.hottest"),
      value: formatTemp(o.hottest.value),
      ...stepMeta(o.hottest.step),
      color: STAT_COLORS.hot,
      iconUrl: weatherIconUrl(o.hottest.step.weather.day.icon),
    });
  }

  if (o.coldest) {
    const coldIcon = o.coldest.isNight
      ? (o.coldest.step.weather.night?.icon ?? o.coldest.step.weather.day.icon)
      : o.coldest.step.weather.day.icon;
    items.push({
      label: t("overview.coldest"),
      value: formatTemp(o.coldest.value),
      ...stepMeta(o.coldest.step),
      color: STAT_COLORS.cold,
      iconUrl: weatherIconUrl(coldIcon),
    });
  }

  return items;
});

/** Two columns: [left half, right half]. */
const factColumns = computed(() => {
  const mid = Math.ceil(allFacts.value.length / 2);
  return [allFacts.value.slice(0, mid), allFacts.value.slice(mid)];
});
</script>

<template>
  <div class="page-container overview" role="region" :aria-label="t('overview.title')">
    <div class="overview-content">
      <template v-for="(col, ci) in factColumns" :key="ci">
        <div class="side-facts" :class="ci === 0 ? 'side-start' : 'side-end'" role="list">
          <div v-for="f in col" :key="f.label" role="listitem" class="fact" :style="{ '--accent': f.color }">
            <div class="fact-icon" aria-hidden="true">
              <img v-if="f.iconUrl" :src="f.iconUrl" class="fact-wx" loading="eager" alt="">
              <q-icon v-else-if="f.iconName" :name="f.iconName" size="1.5rem" class="fact-qi" />
            </div>
            <span class="fact-label">{{ f.label }}</span>
            <span class="fact-value">{{ f.value }}</span>
            <span class="fact-place">{{ f.place }}</span>
            <span class="fact-meta">
              <img :src="flagUrl(f.countryCode)" class="fact-flag" loading="eager" :alt="countryName(f.countryCode, '')">
              <span dir="auto">{{ f.date }}</span>
            </span>
          </div>
        </div>

        <div v-if="ci === 0" class="tapestry">
          <CountrySilhouette
            v-for="item in tapestryItems"
            :key="item.code"
            :country-code="item.code"
            :color="item.color"
            :view-box="combinedViewBox"
            class="tapestry-shape no-pointer-events"
          />
        </div>
      </template>

      <div class="country-labels">
        <div
          v-for="item in tapestryItems"
          :key="item.code"
          class="tapestry-label"
        >
          <img
            :src="flagUrl(item.code)"
            :alt="item.detail"
            class="tapestry-flag"
            loading="eager"
          >
          <span class="tapestry-name" :style="{ color: item.color }" :title="countryName(item.code, item.detail)">
            {{ countryName(item.code, item.detail) }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.overview {
  display: flex;
  flex-direction: column;
  position: relative;

  &::before {
    content: "";
    position: absolute;
    inset: 0;
    z-index: 0;
    background: url("/topo-contours.svg") center / cover no-repeat;
    opacity: 0.22;
    pointer-events: none;
    print-color-adjust: exact;
  }
}

/* ── Grid: facts | silhouettes + labels | facts ── */

.overview-content {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template:
    "start  map  end"  1fr
    / 1fr   3fr  1fr;
  flex: 1;
  padding: var(--page-inset-y) var(--page-inset-x);
  column-gap: var(--gap-md);
  overflow: hidden;
}

/* ── Side facts ───────────────────────────────────── */

.side-facts {
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  min-width: 0;
}

.side-start { grid-area: start; }
.side-end   { grid-area: end; }

/* Stat facts use spacing rhythm to form two visual groups:
   HERO  = icon → label → value  (tight cluster, colored + bright)
   CONTEXT = place → meta        (subordinate, muted tones)
   A generous gap between value and place separates the two. */

.fact {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.fact-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.75rem;
  height: 2.75rem;
  border-radius: var(--radius-full);
  background: color-mix(in srgb, var(--accent) 30%, transparent);
  print-color-adjust: exact;
}

.fact-wx {
  width: 1.5rem;
  height: 1.5rem;
  object-fit: contain;
}

.fact-qi {
  color: var(--accent);
}

.fact-label {
  margin-top: var(--gap-sm);
  font-size: var(--type-3xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: var(--tracking-wider);
  color: var(--accent);
}

.fact-value {
  margin-top: var(--gap-xs);
  font-size: var(--type-2xl);
  font-weight: 800;
  color: var(--text-bright);
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

.fact-place {
  margin-top: var(--gap-md);
  font-size: var(--type-xs);
  font-weight: 400;
  color: var(--text-muted);
  line-height: 1.4;
  overflow-wrap: break-word;
}

.fact-meta {
  display: flex;
  align-items: center;
  gap: var(--gap-md);
  margin-top: var(--gap-xs);
  font-size: var(--type-3xs);
  color: var(--text-faint);
}

.fact-flag {
  width: 1rem;
  height: calc(1rem * 2 / 3); /* 3:2 flag aspect ratio */
  border-radius: var(--radius-xs);
  flex-shrink: 0;
  object-fit: cover;
  border: 0.0625rem solid color-mix(in srgb, var(--text-bright) 22%, transparent);
}

/* ── Silhouette tapestry (center hero) ────────────── */

.tapestry {
  grid-area: map;
  position: relative;
  min-height: 0;
}

.tapestry-shape {
  position: absolute;
  inset: 0;

  :deep(use) {
    stroke: var(--page-bg);
    stroke-width: 12000;
    paint-order: stroke fill;
  }
}

/* ── Country labels (overlaid at bottom of map area) ── */

.country-labels {
  grid-area: map;
  align-self: end;
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--gap-sm) var(--gap-lg);
  padding-bottom: var(--gap-md);
  z-index: 1;
}

.tapestry-label {
  display: flex;
  align-items: center;
  gap: var(--gap-md);
}

.tapestry-flag {
  width: 1.5rem;
  height: calc(1.5rem * 2 / 3);
  border-radius: var(--radius-xs);
  flex-shrink: 0;
  object-fit: cover;
  border: 0.0625rem solid color-mix(in srgb, var(--text-bright) 22%, transparent);
}

.tapestry-name {
  font-size: var(--type-lg);
  font-weight: 800;
  letter-spacing: var(--tracking-tight);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 12rem;
}
</style>
