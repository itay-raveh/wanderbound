<script lang="ts" setup>
import { KM_TO_MI, M_TO_FT } from "@/queries/useUserQuery";
import { useQuasar } from "quasar";
import { computed, useId } from "vue";
import { useI18n } from "vue-i18n";

interface ElevationPoint {
  elevation: number;
  dist: number;
}

const props = defineProps<{
  points: ElevationPoint[];
  accent: string;
  totalDistKm?: number;
  isKm?: boolean;
}>();

const { t } = useI18n();
const $q = useQuasar();
const uid = useId();
const gradId = `elev-gradient-${uid}`;
const fadeId = `elev-bg-fade-${uid}`;

// Layout constants (SVG coordinate space)
const LEFT_PAD = 40;
const RIGHT_PAD = 40;
const TOP_PAD = 8;
const BOTTOM_PAD = 20;
const WIDTH = 500;
const CHART_H = 70;
const FADE_H = 30;
const HEIGHT = CHART_H + FADE_H;
const PLOT_W = WIDTH - LEFT_PAD - RIGHT_PAD;
const PLOT_H = CHART_H - TOP_PAD - BOTTOM_PAD;

const chart = computed(() => {
  if (props.points.length < 2) return null;

  const totalDist = props.totalDistKm ?? props.points[props.points.length - 1]!.dist;
  if (totalDist === 0) return null;

  const elevations = props.points.map((p) => p.elevation);
  const minElev = Math.min(...elevations);
  const maxElev = Math.max(...elevations);
  const range = maxElev - minElev || 1;
  const yMin = minElev - range * 0.1;
  const yRange = range * 1.2;

  const rtl = $q.lang.rtl;
  const toX = (frac: number) => LEFT_PAD + (rtl ? 1 - frac : frac) * PLOT_W;
  const toY = (elev: number) => FADE_H + TOP_PAD + (1 - (elev - yMin) / yRange) * PLOT_H;

  const pixels = props.points.map((p) => ({
    x: toX(p.dist / totalDist),
    y: toY(p.elevation),
  }));

  const linePath = pixels
    .map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`)
    .join(" ");

  const bottomY = FADE_H + TOP_PAD + PLOT_H;
  const areaPath = `${linePath} L${pixels.at(-1)!.x.toFixed(1)},${bottomY} L${pixels[0]!.x.toFixed(1)},${bottomY} Z`;

  return { linePath, areaPath, toX, toY, minElev, maxElev, rtl };
});

const yLabels = computed(() => {
  if (!chart.value) return [];
  const { minElev, maxElev, toY, rtl } = chart.value;
  const midElev = (minElev + maxElev) / 2;
  const factor = props.isKm ? 1 : M_TO_FT;
  return [maxElev, midElev, minElev].map((elev) => ({
    value: Math.round(elev * factor),
    y: toY(elev),
    x: rtl ? LEFT_PAD + PLOT_W + 10 : LEFT_PAD - 4,
    anchor: rtl ? "start" : "end",
  }));
});

const xLabels = computed(() => {
  if (!chart.value) return [];
  const { toX, rtl } = chart.value;
  const totalDist = props.totalDistKm ?? props.points[props.points.length - 1]!.dist;
  const distVal = props.isKm ? totalDist : totalDist * KM_TO_MI;
  const unit = t(props.isKm ? "overview.km" : "overview.mi");
  const fracs = [0, 0.33, 0.67, 1] as const;

  return fracs.map((f, i) => {
    const isFirst = i === 0;
    const isLast = i === fracs.length - 1;
    return {
      text: isLast ? `${distVal.toFixed(1)} ${unit}` : (distVal * f).toFixed(isFirst ? 0 : 1),
      x: toX(f),
      anchor: isFirst ? (rtl ? "end" : "start") : isLast ? (rtl ? "start" : "end") : "middle",
    };
  });
});

const elevUnit = computed(() => t(props.isKm ? "overview.m" : "overview.ft"));
const yAxisX = computed(() => yLabels.value[0]?.x ?? 0);
const yAnchor = computed(() => yLabels.value[0]?.anchor ?? "end");
</script>

<template>
  <svg v-if="chart" :viewBox="`0 0 ${WIDTH} ${HEIGHT}`" class="elevation-chart">
    <defs>
      <linearGradient :id="gradId" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0%" :stop-color="`${accent}55`" />
        <stop offset="100%" :stop-color="`${accent}08`" />
      </linearGradient>
      <linearGradient :id="fadeId" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--bg)" stop-opacity="0" />
        <stop offset="55%" stop-color="var(--bg)" stop-opacity="1" />
        <stop offset="100%" stop-color="var(--bg)" stop-opacity="1" />
      </linearGradient>
    </defs>

    <!-- Background fade (transparent -> solid) -->
    <rect x="0" y="0" :width="WIDTH" :height="HEIGHT" :fill="`url(#${fadeId})`" />

    <!-- Grid lines -->
    <line
      v-for="(l, i) in yLabels"
      :key="`grid-${i}`"
      :x1="LEFT_PAD"
      :y1="l.y"
      :x2="LEFT_PAD + PLOT_W"
      :y2="l.y"
      class="grid-line"
      stroke-width="0.5"
    />

    <!-- Area fill -->
    <path :d="chart.areaPath" :fill="`url(#${gradId})`" />

    <!-- Line stroke -->
    <path :d="chart.linePath" fill="none" :stroke="accent" stroke-width="1.5" stroke-linejoin="round" />

    <!-- Y-axis labels -->
    <text
      v-for="(l, i) in yLabels"
      :key="`y-${i}`"
      :x="l.x"
      :y="l.y + 1"
      :text-anchor="l.anchor"
      class="axis-label"
    >
      {{ l.value }}
    </text>

    <!-- Y-axis unit -->
    <text :x="yAxisX" :y="FADE_H + TOP_PAD - 2" :text-anchor="yAnchor" class="axis-label unit-label">
      {{ elevUnit }}
    </text>

    <!-- X-axis labels -->
    <text
      v-for="(l, i) in xLabels"
      :key="`x-${i}`"
      :x="l.x"
      :y="FADE_H + TOP_PAD + PLOT_H + 11"
      :text-anchor="l.anchor"
      class="axis-label"
    >
      {{ l.text }}
    </text>
  </svg>
</template>

<style lang="scss" scoped>
.elevation-chart {
  display: block;
  width: 100%;
  overflow: visible;
}

.grid-line {
  stroke: color-mix(in srgb, var(--text) 15%, transparent);
  stroke-width: 0.5;
}

.axis-label {
  font-size: 5.5px;
  fill: color-mix(in srgb, var(--text) 75%, transparent);
  font-family: var(--font-body);
  font-weight: 500;
}

.unit-label {
  font-size: 5px;
  fill: color-mix(in srgb, var(--text) 45%, transparent);
}
</style>
