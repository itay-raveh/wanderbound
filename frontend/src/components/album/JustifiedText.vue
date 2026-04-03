<script lang="ts" setup>
import { computed } from "vue";
import type { JustifiedLine } from "@/composables/useTextLayout";

const props = defineProps<{
  lines: JustifiedLine[];
}>();

/** Group flat lines into paragraphs (split on empty-text entries). */
const paragraphs = computed(() => {
  const result: string[][] = [[]];
  for (const line of props.lines) {
    if (!line.text) result.push([]);
    else result.at(-1)!.push(line.text);
  }
  return result;
});
</script>

<template>
  <div class="justified-text">
    <p v-for="(para, i) in paragraphs" :key="i" class="jt-para">
      <template v-for="(text, j) in para" :key="j"><br v-if="j > 0">{{ text }}</template>
    </p>
  </div>
</template>

<style lang="scss" scoped>
.jt-para {
  margin: 0;
  text-align: justify;
  overflow-wrap: break-word;

  &:empty {
    min-height: 1.65em; /* fallback for browsers without lh support */
    min-height: 1lh;
  }
}
</style>
