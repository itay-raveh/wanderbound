<script lang="ts" setup>
import type { Album, Segment, Step } from "@/client";
import { useAlbum } from "@/composables/useAlbum";
import { useUserQuery } from "@/queries/useUserQuery";
import { computed } from "vue";
import { lineString } from "@turf/helpers";
import length from "@turf/length";
import { STAT_COLORS } from "@/utils/colors";
import { flagUrl } from "@/utils/media";
import { symOutlinedCalendarMonth, symOutlinedExplore, symOutlinedPhotoCamera, symOutlinedTimeline } from "@quasar/extras/material-symbols-outlined";
import OverviewExtremes from "./OverviewExtremes.vue";
import OverviewFurthestPoint from "./OverviewFurthestPoint.vue";

const props = defineProps<{
  album: Album;
  steps: Step[];
  segments: Segment[];
}>();

const { totalDays } = useAlbum();
const { user, formatDistance, isKm, locale } = useUserQuery();

const stepsCount = computed(() =>
  props.steps.length.toLocaleString(locale.value),
);

const daysCount = computed(() =>
  totalDays.value.toLocaleString(locale.value),
);

const photosCount = computed(() => {
  let n = 0;
  for (const { pages } of props.steps)
    for (const page of pages) n += page.length;
  return n.toLocaleString(locale.value);
});

const countries = computed(() => {
  const seen = new Map<string, string>();
  for (const { location } of props.steps) {
    if (location.country_code !== "00") {
      seen.set(location.country_code, location.detail);
    }
  }
  return [...seen];
});

const totalDistance = computed(() => {
  const km = props.segments.reduce((acc, seg) => {
    if (seg.points.length < 2) return acc;
    const coords = seg.points.map((p) => [p.lon, p.lat] as [number, number]);
    return acc + length(lineString(coords), { units: "kilometers" });
  }, 0);
  return formatDistance(km);
});

const stats = computed(() => [
  {
    value: daysCount.value,
    label: "Days",
    icon: symOutlinedCalendarMonth,
    color: STAT_COLORS.days,
  },
  {
    value: totalDistance.value,
    label: isKm.value ? "Km" : "Mi",
    icon: symOutlinedExplore,
    color: STAT_COLORS.distance,
  },
  {
    value: photosCount.value,
    label: "Photos",
    icon: symOutlinedPhotoCamera,
    color: STAT_COLORS.photos,
  },
  {
    value: stepsCount.value,
    label: "Steps",
    icon: symOutlinedTimeline,
    color: STAT_COLORS.steps,
  },
]);
</script>

<template>
  <div class="page-container overview relative-position">
    <!-- Content (centered vertically) -->
    <div class="overview-content relative-position">
      <!-- Stats -->
      <div class="stats-row">
        <div
          v-for="(stat, i) in stats"
          :key="i"
          class="stat relative-position overflow-hidden"
          :style="{ '--sc': stat.color }"
        >
          <q-icon :name="stat.icon" size="2.5rem" class="stat-watermark no-pointer-events" />
          <span class="stat-number">{{ stat.value }}</span>
          <span class="stat-label text-muted">{{ stat.label }}</span>
        </div>
      </div>

      <!-- Countries -->
      <div class="countries-strip">
        <div v-for="[code, name] in countries" :key="code" class="country-chip">
          <div
            class="country-accent"
            :style="{
              background: String(album.colors[code] || 'var(--q-primary)'),
            }"
          />
          <img
            :src="flagUrl(code)"
            :alt="name"
            class="country-flag"
            loading="eager"
          >
          <span class="country-name text-bright">{{ name }}</span>
        </div>
      </div>

      <!-- Extremes -->
      <OverviewExtremes :steps="steps" />

      <!-- Furthest point from home -->
      <OverviewFurthestPoint
        v-if="user?.living_location"
        :home="user.living_location"
        :steps="steps"
      />
    </div>

    <!-- Cloud silhouettes (top) -->
    <svg class="clouds no-pointer-events" viewBox="0 0 1200 400" preserveAspectRatio="none">
      <path
        d="M0 200 C150 170, 300 120, 500 150 C700 180, 850 100, 1200 140 L1200 0 L0 0Z"
        fill="var(--text)"
        opacity="0.04"
      />
      <path
        d="M0 140 C200 110, 350 80, 600 100 C850 120, 1000 60, 1200 90 L1200 0 L0 0Z"
        fill="var(--text)"
        opacity="0.06"
      />
      <path
        d="M0 80 C180 60, 400 40, 650 55 C900 70, 1050 30, 1200 50 L1200 0 L0 0Z"
        fill="var(--text)"
        opacity="0.04"
      />
    </svg>

    <!-- Rolling hills (bottom) -->
    <svg class="hills no-pointer-events" viewBox="0 0 1200 400" preserveAspectRatio="none">
      <path
        d="M0 280 C200 230, 350 260, 550 220 C750 180, 950 240, 1200 200 L1200 400 L0 400Z"
        fill="var(--text)"
        opacity="0.04"
      />
      <path
        d="M0 310 C180 270, 400 300, 600 260 C800 230, 1000 280, 1200 250 L1200 400 L0 400Z"
        fill="var(--text)"
        opacity="0.07"
      />
      <path
        d="M0 340 C250 310, 450 330, 650 300 C850 275, 1000 310, 1200 290 L1200 400 L0 400Z"
        fill="var(--text)"
        opacity="0.1"
      />
      <path
        d="M0 365 C200 345, 400 360, 600 340 C800 325, 1000 350, 1200 335 L1200 400 L0 400Z"
        fill="var(--text)"
        opacity="0.13"
      />
    </svg>
  </div>
</template>

<style lang="scss" scoped>
.overview {
  display: flex;
  flex-direction: column;
}

.overview-content {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: var(--gap-lg);
  flex: 1;
  z-index: 1;
}

.clouds {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  width: 100%;
  height: 40%;
}

.hills {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  width: 100%;
  height: 40%;
}

.stats-row {
  display: flex;
  justify-content: space-evenly;
  padding: 0 var(--page-inset-x);
}

.stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--gap-xs);
  padding: 0.5rem 1.5rem;
}

.stat-watermark {
  position: absolute;
  top: 0.125rem;
  right: 0;
  color: var(--sc);
  opacity: 0.1;
}

.stat-number {
  font-size: var(--display-2);
  font-weight: 800;
  color: var(--sc);
  letter-spacing: var(--tracking-tight);
  line-height: 1;
}

.stat-label {
  font-size: var(--type-2xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
}

.countries-strip {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--gap-md) 1.25rem;
  padding: 0.875rem var(--page-inset-x);
  border-top: 1px solid color-mix(in srgb, var(--border-color) 40%, transparent);
  border-bottom: 1px solid
    color-mix(in srgb, var(--border-color) 40%, transparent);
}

.country-chip {
  display: flex;
  align-items: center;
  gap: var(--gap-md);
  padding: 0.375rem 0;
}

.country-accent {
  width: 3px;
  height: 1.375rem;
  border-radius: var(--radius-xs);
  flex-shrink: 0;
}

.country-flag {
  width: 1.625rem;
  height: 1.125rem;
  border-radius: var(--radius-xs);
  flex-shrink: 0;
  object-fit: cover;
}

.country-name {
  font-size: var(--type-md);
  font-weight: 700;
  letter-spacing: var(--tracking-tight);
  white-space: nowrap;
}
</style>
