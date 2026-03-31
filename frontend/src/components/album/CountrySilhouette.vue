<script lang="ts" setup>
import { computed } from "vue";

const props = defineProps<{
  countryCode: string;
  viewBox?: string;
  color?: string;
}>();

const href = computed(() => `/countries/${props.countryCode.toLowerCase()}.svg#map`);
</script>

<template>
  <svg
    class="country-silhouette"
    :viewBox="viewBox"
    :preserveAspectRatio="viewBox ? 'xMidYMid meet' : undefined"
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
