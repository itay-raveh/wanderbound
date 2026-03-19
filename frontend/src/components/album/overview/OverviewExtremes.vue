<script lang="ts" setup>
import type { Step } from "@/client";
import { useUserQuery } from "@/queries/useUserQuery";
import { STAT_COLORS } from "../colors";
import { parseLocalDate } from "@/utils/date";
import { flagUrl, weatherIconUrl } from "@/utils/media";
import { computed } from "vue";
import { matLandscape } from "@quasar/extras/material-icons";

const props = defineProps<{
  steps: Step[];
}>();

const { formatTemp, formatElevation, formatDate } = useUserQuery();

interface ExtremeRecord {
  label: string;
  value: string;
  place: string;
  country: string;
  countryCode: string;
  date: string;
  color: string;
  /** Weather icon URL (temperature records) or Material icon name (elevation). */
  iconUrl?: string;
  iconName?: string;
}

const records = computed<ExtremeRecord[]>(() => {
  const steps = props.steps;
  if (steps.length === 0) return [];

  // Single pass: find coldest (day + night), hottest (day), and highest elevation.
  let cold = { step: steps[0]!, feels: steps[0]!.weather.day.feels_like, isNight: false };
  let hot = { step: steps[0]!, feels: steps[0]!.weather.day.feels_like };
  let highest = steps[0]!;

  for (const step of steps) {
    const dayFeels = step.weather.day.feels_like;
    if (dayFeels < cold.feels) cold = { step, feels: dayFeels, isNight: false };
    if (dayFeels > hot.feels) hot = { step, feels: dayFeels };
    if (step.weather.night && step.weather.night.feels_like < cold.feels) {
      cold = { step, feels: step.weather.night.feels_like, isNight: true };
    }
    if (step.elevation > highest.elevation) highest = step;
  }

  const fmtDate = (s: Step) =>
    formatDate(parseLocalDate(s.datetime), { month: "short", day: "numeric" });

  const meta = (step: Step) => ({
    place: step.name,
    country: step.location.detail,
    countryCode: step.location.country_code,
    date: fmtDate(step),
  });

  const coldIcon = cold.isNight
    ? (cold.step.weather.night?.icon ?? cold.step.weather.day.icon)
    : cold.step.weather.day.icon;

  return [
    { label: "Coldest", value: formatTemp(cold.feels), ...meta(cold.step), color: STAT_COLORS.cold, iconUrl: weatherIconUrl(coldIcon) },
    { label: "Hottest", value: formatTemp(hot.feels), ...meta(hot.step), color: STAT_COLORS.hot, iconUrl: weatherIconUrl(hot.step.weather.day.icon) },
    { label: "Highest", value: formatElevation(highest.elevation), ...meta(highest), color: STAT_COLORS.elevation, iconName: matLandscape },
  ];
});
</script>

<template>
  <div class="extremes">
    <div
      v-for="r in records"
      :key="r.label"
      class="record accent-card"
      :style="{ '--accent': r.color }"
    >
      <div class="record-top">
        <span class="accent-card-tag">{{ r.label }}</span>
        <img v-if="r.iconUrl" :src="r.iconUrl" class="record-wx" alt="" />
        <q-icon v-else-if="r.iconName" :name="r.iconName" size="1.375rem" class="record-q-icon" />
      </div>
      <div class="record-value">{{ r.value }}</div>
      <div class="record-place text-bright">{{ r.place }}</div>
      <div class="record-meta text-muted">
        <img
          :src="flagUrl(r.countryCode)"
          class="record-flag"
          loading="eager"
          alt=""
        >
        <span>{{ r.country }}</span>
        <span class="record-sep">·</span>
        <span dir="auto">{{ r.date }}</span>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.extremes {
  display: flex;
  gap: var(--gap-lg);
  padding: 1.25rem var(--page-inset-x);
  flex-shrink: 0;
}

.record {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--gap-xs);
  min-width: 0;
}

.record-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.record-wx {
  width: 2rem;
  height: 2rem;
  object-fit: contain;
  flex-shrink: 0;
  margin: -0.25rem 0;
}

.record-q-icon {
  color: var(--accent);
  opacity: 0.6;
}

.record-value {
  font-size: var(--type-xl);
  font-weight: 800;
  color: var(--accent);
  letter-spacing: var(--tracking-tight);
  line-height: 1.15;
}

.record-place {
  font-size: var(--type-xs);
  font-weight: 600;
  line-height: 1.3;
  margin-top: var(--gap-xs);
}

.record-meta {
  display: flex;
  align-items: center;
  gap: var(--gap-sm);
  font-size: var(--type-3xs);
  margin-top: 0.0625rem;
}

.record-flag {
  width: 0.875rem;
  height: 0.625rem;
  border-radius: var(--radius-xs);
  flex-shrink: 0;
}

.record-sep {
  opacity: 0.4;
}
</style>
