<script lang="ts" setup>
import type { JustifiedLine } from "@/composables/useTextMeasure";
import EditableText from "../EditableText.vue";

defineProps<{
  lines: JustifiedLine[];
  description: string;
}>();

const emit = defineEmits<{
  "update:description": [description: string];
}>();
</script>

<template>
  <div class="page-container text-page">
    <EditableText
      :model-value="description"
      multiline
      dir="auto"
      class="text-body-columns text-page-body"
      :lines="lines"
      @update:model-value="emit('update:description', $event)"
    />
  </div>
</template>

<style lang="scss" scoped>
.text-page {
  background: var(--bg);
  color: var(--text);
}

.text-page-body {
  width: 100%;
  height: 100%;
}
</style>
