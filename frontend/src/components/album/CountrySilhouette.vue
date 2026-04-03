<script lang="ts" setup>
import { countryBounds } from "@/utils/countryBounds";
import { computed } from "vue";

const props = defineProps<{
  countryCode: string;
  /** Override the default viewBox (derived from countryBounds). */
  viewBox?: string;
  color?: string;
}>();

const href = computed(() => `/countries/${props.countryCode.toLowerCase()}.svg#map`);

const resolvedViewBox = computed(() => {
  if (props.viewBox) return props.viewBox;
  const b = countryBounds[props.countryCode.toLowerCase()];
  return b ? `${b[0]} ${b[1]} ${b[2]} ${b[3]}` : undefined;
});
</script>

<template>
  <svg
    v-if="resolvedViewBox"
    class="country-silhouette"
    :viewBox="resolvedViewBox"
    preserveAspectRatio="xMidYMid meet"
    aria-hidden="true"
  >
    <slot name="defs" />
    <use :href="href" :style="color ? { color } : undefined" />
    <slot />
  </svg>
</template>

<style scoped>
.country-silhouette {
  width: 100%;
  height: 100%;
  overflow: hidden;
}
</style>
