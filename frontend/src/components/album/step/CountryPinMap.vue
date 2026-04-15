<script lang="ts" setup>
import { countryBounds } from "@/utils/countryBounds";
import { toSvgMercator } from "@/utils/geo";
import { colors as qColors } from "quasar";
import { computed } from "vue";
import CountrySilhouette from "../CountrySilhouette.vue";
import { CONTRAST_TEXT_LIGHT } from "../colors";

const props = defineProps<{
  countryCode: string;
  lat: number;
  lon: number;
  color?: string;
}>();

const fillColor = computed(() => props.color ?? "currentColor");
const dotColor = computed(() => {
  if (!props.color) return "currentColor";
  return qColors.lighten(props.color, 40);
});
const strokeColor = CONTRAST_TEXT_LIGHT;

const pin = computed(() => {
  const code = props.countryCode.toLowerCase();
  const b = countryBounds[code];
  if (!b) return null;
  const [x, y] = toSvgMercator(props.lon, props.lat);
  const w = b[2];
  const h = b[3];
  const diag = Math.sqrt(w * w + h * h);
  const r = diag * 0.05;
  return { x, y, r };
});

// Expand viewBox so the pin is never clipped at edges
const viewBox = computed(() => {
  const code = props.countryCode.toLowerCase();
  const b = countryBounds[code];
  if (!b || !pin.value) return b ? `${b[0]} ${b[1]} ${b[2]} ${b[3]}` : null;
  let [minX, minY, w, h] = b;
  const { x, y, r } = pin.value;
  const pad = r * 3;

  if (x - pad < minX) {
    const d = minX - (x - pad);
    minX -= d;
    w += d;
  }
  if (y - pad < minY) {
    const d = minY - (y - pad);
    minY -= d;
    h += d;
  }
  if (x + pad > minX + w) w = x + pad - minX;
  if (y + pad > minY + h) h = y + pad - minY;

  return `${minX} ${minY} ${w} ${h}`;
});
</script>

<template>
  <CountrySilhouette
    v-if="viewBox"
    :country-code="countryCode"
    :view-box="viewBox"
    :color="fillColor"
  >
    <circle
      v-if="pin"
      :cx="pin.x"
      :cy="pin.y"
      :r="pin.r"
      :fill="dotColor"
      :stroke="strokeColor"
      :stroke-width="pin.r * 0.2"
    />
  </CountrySilhouette>
</template>
