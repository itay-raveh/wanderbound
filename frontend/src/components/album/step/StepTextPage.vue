<script lang="ts" setup>
import { usePrintMode } from "@/composables/usePrintReady";
import EditableText from "@/components/EditableText.vue";

defineProps<{
  text: string;
  description: string;
}>();

const emit = defineEmits<{
  "update:description": [description: string];
}>();

const printMode = usePrintMode();
</script>

<template>
  <div class="page-container text-page">
    <EditableText
      v-if="!printMode"
      :model-value="description"
      multiline
      dir="auto"
      class="text-page-body"
      :display-value="text"
      @update:model-value="emit('update:description', $event)"
    />
    <div v-else dir="auto" class="text-page-body">
      {{ text }}
    </div>
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
  padding: var(--page-inset-y) var(--page-inset-x);
  font-size: var(--type-sm);
  line-height: 1.65;
  white-space: pre-wrap;
  text-align: justify;
  column-count: 2;
  column-gap: var(--page-inset-y);
  overflow: hidden;
  box-sizing: border-box;
}
</style>
