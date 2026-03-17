<script lang="ts" setup>
import type { Step } from "@/client";
import { useUserQuery } from "@/queries/useUserQuery";
import { STAT_COLORS } from "@/utils/colors";
import { parseLocalDate } from "@/utils/date";
import { flagUrl } from "@/utils/media";
import { weatherIconUrl } from "@/utils/weather";
import { computed } from "vue";
import { matLandscape } from "@quasar/extras/material-icons";

const props = defineProps<{
  steps: Step[];
}>();

const { formatTemp, formatElevation, formatDate } = useUserQuery();

interface ExtremeRecord {
  type: "temp" | "elev";
  label: string;
  value: string;
  place: string;
  country: string;
  countryCode: string;
  date: string;
  color: string;
  icon: string;
  qIcon: boolean;
}

const records = computed<ExtremeRecord[]>(() => {
  const steps = props.steps;
  if (steps.length === 0) return [];

  // Use feels_like for temperature; check night for coldest
  let coldStep = steps[0]!;
  let coldFeels = coldStep.weather.day.feels_like;
  let coldIsNight = false;

  let hotStep = steps[0]!;
  let hotFeels = hotStep.weather.day.feels_like;

  for (const step of steps) {
    if (step.weather.day.feels_like < coldFeels) {
      coldFeels = step.weather.day.feels_like;
      coldStep = step;
      coldIsNight = false;
    }
    if (step.weather.day.feels_like > hotFeels) {
      hotFeels = step.weather.day.feels_like;
      hotStep = step;
    }
    if (step.weather.night && step.weather.night.feels_like < coldFeels) {
      coldFeels = step.weather.night.feels_like;
      coldStep = step;
      coldIsNight = true;
    }
  }

  // Highest only — lowest is often 0m / uninteresting
  let highestStep = steps[0]!;

  for (const step of steps) {
    if (step.elevation > highestStep.elevation) highestStep = step;
  }

  const meta = (step: Step) => {
    const dateStr = formatDate(parseLocalDate(step.datetime), {
      month: "short",
      day: "numeric",
    });
    return {
      place: step.name,
      country: step.location.detail,
      countryCode: step.location.country_code,
      date: dateStr,
    };
  };

  const coldIcon = coldIsNight
    ? (coldStep.weather.night?.icon ?? coldStep.weather.day.icon)
    : coldStep.weather.day.icon;

  return [
    {
      type: "temp",
      label: "Coldest",
      value: formatTemp(coldFeels),
      ...meta(coldStep),
      color: STAT_COLORS.cold,
      icon: weatherIconUrl(coldIcon),
      qIcon: false,
    },
    {
      type: "temp",
      label: "Hottest",
      value: formatTemp(hotFeels),
      ...meta(hotStep),
      color: STAT_COLORS.hot,
      icon: weatherIconUrl(hotStep.weather.day.icon),
      qIcon: false,
    },
    {
      type: "elev",
      label: "Highest",
      value: formatElevation(highestStep.elevation),
      ...meta(highestStep),
      color: STAT_COLORS.elevation,
      icon: matLandscape,
      qIcon: true,
    },
  ];
});
</script>

<template>
  <div class="extremes">
    <div
      v-for="r in records"
      :key="r.label"
      class="record"
      :style="{ '--accent': r.color }"
    >
      <div class="record-top">
        <span class="record-tag">{{ r.label }}</span>
        <img v-if="!r.qIcon" :src="r.icon" class="record-wx" alt="" />
        <q-icon v-else :name="r.icon" size="1.375rem" class="record-q-icon" />
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
  padding: 0.625rem 0.75rem;
  border-left: 3px solid var(--accent);
  background: color-mix(in srgb, var(--accent) 6%, var(--page-bg, var(--bg)));
  border-radius: var(--radius-sm);
  min-width: 0;
}

.record-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.record-tag {
  font-size: var(--type-3xs);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  color: var(--accent);
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
