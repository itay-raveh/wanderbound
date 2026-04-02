<script lang="ts" setup>
import { KM_TO_MI, M_TO_FT } from "@/queries/useUserQuery";
import { scaleLinear } from "d3-scale";
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

// Fixed SVG coordinate space — CSS controls the visual size via the container.
// The SVG scales to fill its container while preserving this aspect ratio.
const W = 500;
const H = 70;
const PAD = { top: 4, right: 8, bottom: 10, left: 20 };
const PLOT_W = W - PAD.left - PAD.right;
const PLOT_H = H - PAD.top - PAD.bottom;

const chart = computed(() => {
  if (props.points.length < 2) return null;

  const lastDist = props.points[props.points.length - 1]!.dist;
  if (lastDist === 0) return null;

  const elevFactor = props.isKm ? 1 : M_TO_FT;
  const distFactor = props.isKm ? 1 : KM_TO_MI;
  const elevations = props.points.map((p) => p.elevation * elevFactor);

  // d3 scaleLinear: domain = data units, range = SVG coordinates.
  // No .nice() — data fills the chart. ticks() still picks round values.
  // Small top padding so the highest tick label isn't clipped by the viewBox.
  const yMin = Math.min(...elevations);
  const yMax = Math.max(...elevations);
  const y = scaleLinear()
    .domain([yMin, yMax + (yMax - yMin) * 0.05])
    .range([PAD.top + PLOT_H, PAD.top]);

  const x = scaleLinear()
    .domain([0, lastDist * distFactor])
    .range([PAD.left, PAD.left + PLOT_W]);

  // Hide the zero tick on y-axis (it's the implicit axis baseline)
  const allYTicks = y.ticks(4);
  const yTicks = allYTicks[0] === 0 ? allYTicks.slice(1) : allYTicks;
  // Skip the 0-tick on x-axis (y-axis already anchors the origin)
  const xTicks = x.ticks(5).filter((v) => v > 0);

  const toX = (dist: number) => x(dist * distFactor);
  const toY = (elev: number) => y(elev * elevFactor);

  const pixels = props.points.map((p) => ({
    x: toX(p.dist),
    y: toY(p.elevation),
  }));

  const linePath = pixels
    .map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`)
    .join(" ");

  const bottomY = PAD.top + PLOT_H;
  const areaPath = `${linePath} L${pixels.at(-1)!.x.toFixed(1)},${bottomY} L${pixels[0]!.x.toFixed(1)},${bottomY} Z`;

  return { linePath, areaPath, toX, toY, yTicks, xTicks };
});

const yLabels = computed(() => {
  if (!chart.value) return [];
  const { yTicks, toY } = chart.value;
  const elevFactor = props.isKm ? 1 : M_TO_FT;
  return yTicks.map((value) => ({
    value,
    y: toY(value / elevFactor),
    x: PAD.left - 2,
    anchor: "end" as const,
  }));
});

const xLabels = computed(() => {
  if (!chart.value) return [];
  const { xTicks, toX } = chart.value;
  const unit = t(props.isKm ? "overview.km" : "overview.mi");
  const distFactor = props.isKm ? 1 : KM_TO_MI;

  return xTicks.map((value, i, arr) => {
    const isLast = i === arr.length - 1;
    return {
      text: isLast ? `${value} ${unit}` : String(value),
      x: toX(value / distFactor),
      anchor: isLast ? ("end" as const) : ("middle" as const),
    };
  });
});

const elevUnit = computed(() => t(props.isKm ? "overview.m" : "overview.ft"));
const unitY = computed(() => (yLabels.value.at(-1)?.y ?? PAD.top) - 4);
</script>

<template>
  <div class="elevation-chart">
    <svg v-if="chart" :viewBox="`0 0 ${W} ${H}`" direction="ltr" role="img" :aria-label="t('hike.elevationProfile')">
      <defs>
        <linearGradient :id="gradId" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" :stop-color="accent" stop-opacity="0.33" />
          <stop offset="100%" :stop-color="accent" stop-opacity="0.03" />
        </linearGradient>
      </defs>

      <!-- Grid lines -->
      <line
        v-for="(l, i) in yLabels"
        :key="`grid-${i}`"
        :x1="PAD.left"
        :y1="l.y"
        :x2="PAD.left + PLOT_W"
        :y2="l.y"
        class="grid-line"
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
        :y="l.y + 0.5"
        :text-anchor="l.anchor"
        class="axis-label"
      >
        {{ l.value }}
      </text>

      <!-- Y-axis unit -->
      <text :x="PAD.left - 2" :y="unitY" text-anchor="end" class="axis-label unit-label">
        {{ elevUnit }}
      </text>

      <!-- X-axis labels -->
      <text
        v-for="(l, i) in xLabels"
        :key="`x-${i}`"
        :x="l.x"
        :y="PAD.top + PLOT_H + 8"
        :text-anchor="l.anchor"
        class="axis-label"
      >
        {{ l.text }}
      </text>
    </svg>
  </div>
</template>

<style lang="scss" scoped>
.elevation-chart {
  width: 100%;
  print-color-adjust: exact;

  svg {
    display: block;
    width: 100%;
    height: auto;
  }
}

.grid-line {
  stroke: color-mix(in srgb, var(--text) 30%, transparent);
  stroke-width: 0.25;
}

.axis-label {
  font-size: 5.5px;
  fill: color-mix(in srgb, var(--text) 90%, transparent);
  font-family: var(--font-ui);
  font-weight: 500;
}

.unit-label {
  font-size: 5px;
  fill: color-mix(in srgb, var(--text) 60%, transparent);
}
</style>
