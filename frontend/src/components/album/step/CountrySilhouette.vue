<script lang="ts" setup>
import { ref, computed, watch } from "vue";

const props = defineProps<{
  countryCode: string;
  lat: number;
  lon: number;
  color?: string;
}>();

const pathContent = ref("");
const rawViewBox = ref("");

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
  if (!rawViewBox.value) return null;
  const [x, y] = toSvgCoords(props.lat, props.lon);
  const parts = rawViewBox.value.split(" ").map(Number);
  const w = parts[2]!;
  const h = parts[3]!;
  // Use diagonal to get consistent visual size regardless of country aspect ratio
  const diag = Math.sqrt(w * w + h * h);
  const r = diag * 0.025;
  return { x, y, r };
});

// Expand viewBox so the pin is never clipped at edges
const viewBox = computed(() => {
  if (!rawViewBox.value || !pin.value) return rawViewBox.value;
  const parts = rawViewBox.value.split(" ").map(Number);
  let [minX, minY, w, h] = parts as [number, number, number, number];
  const { x, y, r } = pin.value;
  const pad = r * 3;

  if (x - pad < minX) { const d = minX - (x - pad); minX -= d; w += d; }
  if (y - pad < minY) { const d = minY - (y - pad); minY -= d; h += d; }
  if (x + pad > minX + w) w = x + pad - minX;
  if (y + pad > minY + h) h = y + pad - minY;

  return `${minX} ${minY} ${w} ${h}`;
});

async function loadSvg(code: string) {
  try {
    const res = await fetch(`/countries/${code}.svg`);
    if (!res.ok) return;
    const text = await res.text();

    const vbMatch = text.match(/viewBox="([^"]+)"/);
    if (vbMatch) rawViewBox.value = vbMatch[1]!;

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
    <defs>
      <filter :id="`glow-${countryCode}`" x="-50%" y="-50%" width="200%" height="200%">
        <feGaussianBlur in="SourceGraphic" :stdDeviation="pin ? pin.r * 0.8 : 2" result="blur" />
        <feMerge>
          <feMergeNode in="blur" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
    </defs>
    <!-- eslint-disable vue/no-v-html -->
    <g :style="{ color: fillColor }" v-html="pathContent" />
    <circle
      v-if="pin"
      :cx="pin.x"
      :cy="pin.y"
      :r="pin.r"
      fill="white"
      :filter="`url(#glow-${countryCode})`"
    />
  </svg>
</template>

<style scoped>
.country-silhouette {
  width: 100%;
  height: 100%;
}
</style>
