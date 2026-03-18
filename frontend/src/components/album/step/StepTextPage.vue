<script lang="ts" setup>
import EditableText from "@/components/EditableText.vue";

defineProps<{
  text: string;
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
      class="text-page-body"
      :display-value="text"
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
