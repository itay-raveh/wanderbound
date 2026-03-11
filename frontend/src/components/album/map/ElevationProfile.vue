<script lang="ts" setup>
import { distance, point } from "@turf/turf";
import { computed } from "vue";

interface ElevationPoint {
  lat: number;
  lon: number;
  elevation: number;
}

const props = defineProps<{
  points: ElevationPoint[];
  accent: string;
}>();

const profileData = computed(() => {
  if (props.points.length < 2) return { path: "", viewBox: "0 0 100 50" };

  // Cumulative distance along the track
  const distances: number[] = [0];
  for (let i = 1; i < props.points.length; i++) {
    const prev = props.points[i - 1]!;
    const curr = props.points[i]!;
    const d = distance(
      point([prev.lon, prev.lat]),
      point([curr.lon, curr.lat]),
      { units: "kilometers" },
    );
    distances.push(distances[i - 1]! + d);
  }

  const totalDist = distances[distances.length - 1]!;
  if (totalDist === 0) return { path: "", viewBox: "0 0 100 50" };

  const values = props.points.map((p) => p.elevation);
  const minVal = Math.min(...values);
  const maxVal = Math.max(...values);
  const range = maxVal - minVal || 1;

  const width = 400;
  const height = 80;
  const pad = 4;

  // Downsample to max 200 points for the SVG path
  const step = Math.max(1, Math.floor(props.points.length / 200));
  const sampled: { x: number; y: number }[] = [];

  for (let i = 0; i < props.points.length; i += step) {
    const x = pad + (distances[i]! / totalDist) * (width - 2 * pad);
    const normalized = (values[i]! - minVal) / range;
    const y = height - pad - normalized * (height - 2 * pad);
    sampled.push({ x, y });
  }

  if (sampled.length === 0)
    return { path: "", viewBox: `0 0 ${width} ${height}` };

  const linePath = sampled
    .map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`)
    .join(" ");

  const last = sampled[sampled.length - 1]!;
  const first = sampled[0]!;
  const areaPath = `${linePath} L${last.x},${height - pad} L${first.x},${height - pad} Z`;

  return {
    linePath,
    areaPath,
    viewBox: `0 0 ${width} ${height}`,
  };
});
</script>

<template>
  <svg
    :viewBox="profileData.viewBox"
    class="elevation-chart"
    preserveAspectRatio="none"
  >
    <defs>
      <linearGradient id="elev-gradient" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0%" :stop-color="`${accent}66`" />
        <stop offset="100%" :stop-color="`${accent}0D`" />
      </linearGradient>
    </defs>
    <path
      v-if="profileData.areaPath"
      :d="profileData.areaPath"
      fill="url(#elev-gradient)"
    />
    <path
      v-if="profileData.linePath"
      :d="profileData.linePath"
      fill="none"
      :stroke="accent"
      stroke-width="1.5"
    />
  </svg>
</template>

<style lang="scss" scoped>
.elevation-chart {
  width: 100%;
  height: 100%;
}
</style>
