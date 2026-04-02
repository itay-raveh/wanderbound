<script lang="ts" setup>
import type { JustifiedLine } from "@/composables/useTextMeasure";

defineProps<{
  lines: JustifiedLine[];
}>();
</script>

<template>
  <div class="justified-text">
    <span
      v-for="(line, i) in lines"
      :key="i"
      class="jt-line"
      :style="line.wordSpacing ? { wordSpacing: line.wordSpacing + 'px' } : undefined"
    >{{ line.text }}</span>
  </div>
</template>

<style lang="scss" scoped>
.jt-line {
  display: block;
  white-space: pre; // prevent re-wrapping — lines are pre-broken by Knuth-Plass
}
</style>
