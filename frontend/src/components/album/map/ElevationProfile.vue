<script lang="ts" setup>
import { KM_TO_MI, M_TO_FT } from "@/utils/units";
import { computed } from "vue";

interface ElevationPoint {
  elevation: number;
  dist: number;
}

const props = defineProps<{
  points: ElevationPoint[];
  accent: string;
  totalDistKm?: number;
  isKm?: boolean;
  /** When set, extends the SVG upward with a gradient fade from transparent to this color. */
  bgColor?: string;
}>();

const chart = computed(() => {
  if (props.points.length < 2) return null;

  const totalDist =
    props.totalDistKm ?? props.points[props.points.length - 1]!.dist;
  if (totalDist === 0) return null;

  const elevations = props.points.map((p) => p.elevation);
  const minElev = Math.min(...elevations);
  const maxElev = Math.max(...elevations);
  const range = maxElev - minElev || 1;

  // Add ~10% padding above and below
  const padded = range * 0.1;
  const yMin = minElev - padded;
  const yMax = maxElev + padded;
  const yRange = yMax - yMin;

  // Layout constants
  const leftPad = 42; // space for Y-axis labels
  const rightPad = 32;
  const topPad = 8;
  const bottomPad = 24; // space for X-axis labels
  const width = 500;
  const chartH = 82;
  // When bgColor is set, extend upward for the gradient fade area
  const fadeH = props.bgColor ? 54 : 0;
  const height = chartH + fadeH;
  // Offset all Y coords by fadeH so chart content stays at the bottom
  const yOff = fadeH;
  const plotW = width - leftPad - rightPad;
  const plotH = chartH - topPad - bottomPad;

  // Map data to pixel coords (yOff shifts everything down when fade area is present)
  const dataPoints = props.points.map((p) => ({
    x: leftPad + (p.dist / totalDist) * plotW,
    y: yOff + topPad + (1 - (p.elevation - yMin) / yRange) * plotH,
  }));

  const linePath = dataPoints
    .map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`)
    .join(" ");

  const last = dataPoints[dataPoints.length - 1]!;
  const first = dataPoints[0]!;
  const areaPath = `${linePath} L${last.x.toFixed(1)},${yOff + topPad + plotH} L${first.x.toFixed(1)},${yOff + topPad + plotH} Z`;

  // Unit conversion for displayed values
  const elevFactor = props.isKm ? 1 : M_TO_FT;

  // Y-axis labels (min, mid, max) — converted to display units
  const midElev = (minElev + maxElev) / 2;
  const yLabels = [
    {
      value: Math.round(maxElev * elevFactor),
      y: yOff + topPad + (1 - (maxElev - yMin) / yRange) * plotH,
    },
    {
      value: Math.round(midElev * elevFactor),
      y: yOff + topPad + (1 - (midElev - yMin) / yRange) * plotH,
    },
    {
      value: Math.round(minElev * elevFactor),
      y: yOff + topPad + (1 - (minElev - yMin) / yRange) * plotH,
    },
  ];
  const elevUnit = props.isKm ? "m" : "ft";

  // X-axis labels: 0, ~1/3, ~2/3, end
  const distKm = totalDist;
  const unit = props.isKm ? "km" : "mi";
  const distVal = props.isKm ? distKm : distKm * KM_TO_MI;
  const fracs = [0, 0.33, 0.67, 1];
  const xLabels = fracs.map((f) => ({
    text: (distVal * f).toFixed(f === 0 ? 0 : 1),
    x: leftPad + f * plotW,
  }));

  // Horizontal grid lines at each Y label
  const gridLines = yLabels.map((l) => ({
    y: l.y,
    x1: leftPad,
    x2: leftPad + plotW,
  }));

  return {
    linePath,
    areaPath,
    viewBox: `0 0 ${width} ${height}`,
    yLabels,
    elevUnit,
    xLabels,
    gridLines,
    unit,
    leftPad,
    plotW,
    topPad: yOff + topPad,
    plotH,
    fadeH,
    width,
    height,
  };
});
</script>

<template>
  <svg v-if="chart" :viewBox="chart.viewBox" class="elevation-chart">
    <defs>
      <linearGradient id="elev-gradient" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0%" :stop-color="`${accent}55`" />
        <stop offset="100%" :stop-color="`${accent}08`" />
      </linearGradient>
      <linearGradient
        v-if="bgColor"
        id="elev-bg-fade"
        x1="0"
        y1="0"
        x2="0"
        y2="1"
      >
        <stop offset="0%" :stop-color="bgColor" stop-opacity="0" />
        <stop offset="55%" :stop-color="bgColor" stop-opacity="1" />
        <stop offset="100%" :stop-color="bgColor" stop-opacity="1" />
      </linearGradient>
    </defs>

    <!-- Background fade (transparent → solid) -->
    <rect
      v-if="bgColor"
      x="0"
      y="0"
      :width="chart.width"
      :height="chart.height"
      fill="url(#elev-bg-fade)"
    />

    <!-- Grid lines -->
    <line
      v-for="(g, i) in chart.gridLines"
      :key="`grid-${i}`"
      :x1="g.x1"
      :y1="g.y"
      :x2="g.x2"
      :y2="g.y"
      stroke="rgba(255,255,255,0.15)"
      stroke-width="0.5"
    />

    <!-- Area fill -->
    <path :d="chart.areaPath" fill="url(#elev-gradient)" />

    <!-- Line stroke -->
    <path
      :d="chart.linePath"
      fill="none"
      :stroke="accent"
      stroke-width="1.5"
      stroke-linejoin="round"
    />

    <!-- Y-axis labels (elevation in m or ft) -->
    <text
      v-for="(l, i) in chart.yLabels"
      :key="`y-${i}`"
      :x="chart.leftPad - 4"
      :y="l.y + 1"
      text-anchor="end"
      class="axis-label"
    >
      {{ l.value }}
    </text>

    <!-- Y-axis unit -->
    <text
      :x="chart.leftPad - 4"
      :y="chart.topPad - 1"
      text-anchor="end"
      class="axis-label unit-label"
    >
      {{ chart.elevUnit }}
    </text>

    <!-- X-axis labels (distance) -->
    <text
      v-for="(l, i) in chart.xLabels"
      :key="`x-${i}`"
      :x="l.x"
      :y="chart.topPad + chart.plotH + 11"
      :text-anchor="
        i === 0 ? 'start' : i === chart.xLabels.length - 1 ? 'end' : 'middle'
      "
      class="axis-label"
    >
      {{ l.text }}
    </text>

    <!-- Unit label at end -->
    <text
      :x="chart.leftPad + chart.plotW"
      :y="chart.topPad + chart.plotH + 11"
      text-anchor="start"
      class="axis-label unit-label"
    >
      {{ chart.unit }}
    </text>
  </svg>
</template>

<style lang="scss" scoped>
.elevation-chart {
  width: 100%;
  overflow: visible;
}

.axis-label {
  font-size: 5.5px;
  fill: rgba(255, 255, 255, 0.75);
  font-family: "Inter", system-ui, sans-serif;
  font-weight: 500;
}

.unit-label {
  font-size: 5px;
  fill: rgba(255, 255, 255, 0.45);
}
</style>
