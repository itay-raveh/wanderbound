<script lang="ts" setup>
import countryBounds from "@/countries/bounds.json";
import { computed } from "vue";

const props = defineProps<{
  countryCode: string;
  lat: number;
  lon: number;
  color?: string;
}>();

const bounds = countryBounds as Record<string, [number, number, number, number]>;

const fillColor = computed(() => props.color ?? "currentColor");
const code = computed(() => props.countryCode.toLowerCase());
const svgHref = computed(() => `/countries/${code.value}.svg#map`);

const rawViewBox = computed(() => {
  const b = bounds[code.value];
  return b ? `${b[0]} ${b[1]} ${b[2]} ${b[3]}` : null;
});

// Convert lat/lon → Web Mercator (EPSG:3857), then flip Y (matching the SVG generation script)
function toSvgCoords(lat: number, lon: number): [number, number] {
  const x = (lon * 20037508.34) / 180;
  const latRad = (lat * Math.PI) / 180;
  const y =
    (Math.log(Math.tan(Math.PI / 4 + latRad / 2)) * 20037508.34) / Math.PI;
  return [x, -y];
}

const pin = computed(() => {
  const b = bounds[code.value];
  if (!b) return null;
  const [x, y] = toSvgCoords(props.lat, props.lon);
  const w = b[2];
  const h = b[3];
  const diag = Math.sqrt(w * w + h * h);
  const r = diag * 0.025;
  return { x, y, r };
});

// Expand viewBox so the pin is never clipped at edges
const viewBox = computed(() => {
  if (!rawViewBox.value || !pin.value) return rawViewBox.value;
  const b = bounds[code.value]!;
  let [minX, minY, w, h] = b;
  const { x, y, r } = pin.value;
  const pad = r * 3;

  if (x - pad < minX) { const d = minX - (x - pad); minX -= d; w += d; }
  if (y - pad < minY) { const d = minY - (y - pad); minY -= d; h += d; }
  if (x + pad > minX + w) w = x + pad - minX;
  if (y + pad > minY + h) h = y + pad - minY;

  return `${minX} ${minY} ${w} ${h}`;
});
</script>

<template>
  <svg
    v-if="viewBox"
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
    <use :href="svgHref" :style="{ color: fillColor }" />
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
