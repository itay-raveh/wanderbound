<script lang="ts" setup>
import { ref, computed, watch } from "vue";

const props = defineProps<{
  countryCode: string;
  lat: number;
  lon: number;
  color?: string;
}>();

const pathContent = ref("");
const viewBox = ref("");

const fillColor = computed(() => props.color ?? "currentColor");

// Convert lat/lon → Web Mercator (EPSG:3857), then flip Y (matching the SVG generation script)
function toSvgCoords(lat: number, lon: number): [number, number] {
  const x = (lon * 20037508.34) / 180;
  const latRad = (lat * Math.PI) / 180;
  const y =
    (Math.log(Math.tan(Math.PI / 4 + latRad / 2)) * 20037508.34) / Math.PI;
  return [x, -y];
}

const pin = computed(() => {
  if (!viewBox.value) return null;
  const [x, y] = toSvgCoords(props.lat, props.lon);
  const parts = viewBox.value.split(" ").map(Number);
  const w = parts[2]!;
  // Pin radius relative to viewBox size
  const r = w * 0.03;
  return { x, y, r };
});

async function loadSvg(code: string) {
  try {
    const res = await fetch(`/countries/${code}.svg`);
    if (!res.ok) return;
    const text = await res.text();

    const vbMatch = text.match(/viewBox="([^"]+)"/);
    if (vbMatch) viewBox.value = vbMatch[1]!;

    const innerMatch = text.match(/<symbol[^>]*>([\s\S]*?)<\/symbol>/);
    if (innerMatch) pathContent.value = innerMatch[1]!;
  } catch {
    /* country SVG not available */
  }
}

watch(
  () => props.countryCode,
  (code) => {
    if (code) void loadSvg(code.toLowerCase());
  },
  { immediate: true },
);
</script>

<template>
  <svg
    v-if="viewBox && pathContent"
    :viewBox="viewBox"
    class="country-silhouette"
    preserveAspectRatio="xMidYMid meet"
  >
    <!-- eslint-disable vue/no-v-html -->
    <g :style="{ color: fillColor }" v-html="pathContent" />
    <circle
      v-if="pin"
      :cx="pin.x"
      :cy="pin.y"
      :r="pin.r"
      fill="var(--q-primary)"
      stroke="white"
      :stroke-width="pin.r * 0.4"
    />
  </svg>
</template>

<style scoped>
.country-silhouette {
  width: 100%;
  height: 100%;
}
</style>
