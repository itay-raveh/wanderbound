<script lang="ts" setup>
import { computed } from "vue";
import type { JustifiedLine } from "@/composables/useTextLayout";

const props = defineProps<{
  lines: JustifiedLine[];
}>();

/** Group flat lines into paragraphs (split on empty-text entries).
 *  The very last line is pulled into its own non-justified block so that
 *  if overflow: hidden clips it, the preceding line becomes the last line
 *  of its <p> and the browser naturally skips justification for it. */
const paragraphs = computed(() => {
  const allButLast = props.lines.slice(0, -1);
  if (allButLast.length === 0) return [];
  const result: string[][] = [[]];
  for (const line of allButLast) {
    if (!line.text) result.push([]);
    else result.at(-1)!.push(line.text);
  }
  return result;
});

const lastLine = computed(() => props.lines.at(-1)?.text ?? null);
</script>

<template>
  <div class="justified-text">
    <p v-for="(para, i) in paragraphs" :key="i" class="jt-para">
      <template v-for="(text, j) in para" :key="j"><br v-if="j > 0">{{ text }}</template>
    </p>
    <p v-if="lastLine" class="jt-last">{{ lastLine }}</p>
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

/* Page-ending line: not justified, so clipping it via overflow: hidden
   means the preceding line (now last of its <p>) is also unjustified. */
.jt-last {
  margin: 0;
  overflow-wrap: break-word;
}
</style>
