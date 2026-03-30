<script lang="ts" setup>
import { KM_TO_MI, M_TO_FT } from "@/queries/useUserQuery";
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
const uid = useId();
const gradId = `elev-gradient-${uid}`;
const fadeId = `elev-bg-fade-${uid}`;

// Layout constants (SVG coordinate space)
const LEFT_PAD = 40;
const RIGHT_PAD = 8;
const TOP_PAD = 8;
const BOTTOM_PAD = 20;
const WIDTH = 500;
const CHART_H = 70;
const FADE_H = 30;
const HEIGHT = CHART_H + FADE_H;
const PLOT_W = WIDTH - LEFT_PAD - RIGHT_PAD;
const PLOT_H = CHART_H - TOP_PAD - BOTTOM_PAD;

/** Nice round multipliers in ascending order within a decade. */
const NICE_STEPS = [1, 2, 5, 10];

/** Generate nice ticks covering [lo, hi] with at most `maxTicks` values. */
function niceTicks(lo: number, hi: number, maxTicks: number): number[] {
  const range = hi - lo;
  if (range === 0) return [Math.round(lo)];

  // Start with the smallest nice step and increase until tick count fits
  const mag = 10 ** Math.floor(Math.log10(range / maxTicks));
  for (const nice of NICE_STEPS) {
    const step = nice * mag;
    const tickLo = Math.floor(lo / step) * step;
    const tickHi = Math.ceil(hi / step) * step;
    const count = Math.round((tickHi - tickLo) / step) + 1;
    if (count <= maxTicks) {
      const ticks: number[] = [];
      for (let v = tickLo; v <= tickHi + step * 0.01; v += step) ticks.push(Math.round(v));
      return ticks;
    }
  }
  // Fallback: use 10 * mag (shouldn't reach here)
  return niceTicks(lo, hi, maxTicks + 1);
}

const chart = computed(() => {
  if (props.points.length < 2) return null;

  const totalDist = props.totalDistKm ?? props.points[props.points.length - 1]!.dist;
  if (totalDist === 0) return null;

  const elevations = props.points.map((p) => p.elevation);
  const minElev = Math.min(...elevations);
  const maxElev = Math.max(...elevations);

  // Y-axis: nice ticks in display units, always ~3 ticks
  const elevFactor = props.isKm ? 1 : M_TO_FT;
  const yTicks = niceTicks(minElev * elevFactor, maxElev * elevFactor, 3);
  const tickLo = yTicks[0]!;
  const tickHi = yTicks[yTicks.length - 1]!;

  // Scale covers tick range + 5% padding so ticks aren't flush with plot edges
  const tickRange = (tickHi - tickLo) / elevFactor || 1;
  const yMin = tickLo / elevFactor - tickRange * 0.05;
  const yRange = tickRange * 1.1;

  // Graphs are math — always left-to-right regardless of document direction
  const toX = (frac: number) => LEFT_PAD + frac * PLOT_W;
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

  // X-axis: nice ticks in display units, ~5 ticks
  const distFactor = props.isKm ? 1 : KM_TO_MI;
  const distDisplay = totalDist * distFactor;
  const xTicks = niceTicks(0, distDisplay, 5);

  return { linePath, areaPath, toX, toY, yTicks, xTicks, totalDist, distDisplay };
});

const yLabels = computed(() => {
  if (!chart.value) return [];
  const { yTicks, toY } = chart.value;
  const elevFactor = props.isKm ? 1 : M_TO_FT;
  return yTicks.map((value) => ({
    value,
    y: toY(value / elevFactor),
    x: LEFT_PAD - 4,
    anchor: "end" as const,
  }));
});

const xLabels = computed(() => {
  if (!chart.value) return [];
  const { xTicks, toX, distDisplay } = chart.value;
  const unit = t(props.isKm ? "overview.km" : "overview.mi");

  return xTicks.map((value, i) => {
    const frac = distDisplay > 0 ? value / distDisplay : 0;
    const isFirst = i === 0;
    const isLast = i === xTicks.length - 1;
    return {
      text: isLast ? `${value} ${unit}` : String(value),
      x: toX(frac),
      anchor: isFirst ? ("start" as const) : isLast ? ("end" as const) : ("middle" as const),
    };
  });
});

const elevUnit = computed(() => t(props.isKm ? "overview.m" : "overview.ft"));
const unitY = computed(() => (yLabels.value.at(-1)?.y ?? FADE_H + TOP_PAD) - 6);
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
    <text :x="LEFT_PAD - 4" :y="unitY" text-anchor="end" class="axis-label unit-label">
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
  font-family: var(--font-ui);
  font-weight: 500;
}

.unit-label {
  font-size: 5px;
  fill: color-mix(in srgb, var(--text) 45%, transparent);
}
</style>
