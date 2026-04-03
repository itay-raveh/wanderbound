<script lang="ts" setup>
import type { JustifiedLine } from "@/composables/useTextLayout";
import { usePrintMode } from "@/composables/usePrintReady";
import JustifiedText from "./JustifiedText.vue";
import { ref, nextTick } from "vue";

const props = withDefaults(
  defineProps<{
    modelValue: string;
    multiline?: boolean;
    placeholder?: string;
    lines?: JustifiedLine[] | null;
  }>(),
  { multiline: false, placeholder: "" },
);

const emit = defineEmits<{
  "update:modelValue": [value: string];
}>();

const printMode = usePrintMode();
const editing = ref(false);
const editEl = ref<HTMLTextAreaElement | HTMLElement | null>(null);

function startEdit() {
  editing.value = true;
  void nextTick(() => (editEl.value as HTMLElement)?.focus());
}

function commit() {
  if (!editing.value) return;
  editing.value = false;
  const raw = editEl.value instanceof HTMLTextAreaElement
    ? editEl.value.value
    : editEl.value?.innerText ?? "";
  const text = props.multiline
    ? raw.replace(/\r\n/g, "\n").replace(/^\n+|\n+$/g, "")
    : raw.trim();
  if (text !== props.modelValue) emit("update:modelValue", text);
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") {
    if (!props.multiline && editEl.value) {
      (editEl.value as HTMLElement).textContent = props.modelValue;
    }
    editing.value = false;
    (e.target as HTMLElement).blur();
  } else if (!props.multiline && e.key === "Enter") {
    e.preventDefault();
    (e.target as HTMLElement).blur();
  }
}
</script>

<template>
  <!-- Print mode -->
  <JustifiedText v-if="printMode && lines" :lines="lines" />
  <div v-else-if="printMode">{{ modelValue }}</div>

  <!-- Multiline edit: plain textarea, no DOM conflicts with Vue -->
  <textarea
    v-else-if="multiline && editing"
    ref="editEl"
    class="edit-textarea"
    :value="modelValue"
    :placeholder="placeholder"
    :aria-label="placeholder || undefined"
    @blur="commit"
    @keydown="onKeydown"
  />

  <!-- Multiline display: justified text, click to edit -->
  <div
    v-else-if="multiline"
    role="button"
    tabindex="0"
    class="editable-display"
    :data-placeholder="placeholder"
    @click="startEdit"
    @keydown.enter.prevent="startEdit"
    @keydown.space.prevent="startEdit"
  >
    <JustifiedText v-if="lines" :lines="lines" />
    <template v-else>{{ modelValue }}</template>
  </div>

  <!-- Single-line: inline contenteditable (no justification needed) -->
  <div
    v-else
    ref="editEl"
    role="textbox"
    :aria-label="placeholder || undefined"
    class="editable-display"
    contenteditable="plaintext-only"
    :data-placeholder="placeholder"
    :spellcheck="editing"
    @focus="editing = true"
    @blur="commit"
    @keydown="onKeydown"
  >{{ modelValue }}</div>
</template>

<style lang="scss" scoped>
$outline: 0.125rem dashed color-mix(in srgb, currentColor 35%, transparent);

.editable-display {
  cursor: text;
  border-radius: var(--radius-xs);
  box-decoration-break: clone;
  outline: $outline;
  outline-offset: var(--gap-sm);
  transition: outline-color var(--duration-fast) ease;

  &:hover {
    outline-color: color-mix(in srgb, currentColor 55%, transparent);
  }

  @media (prefers-reduced-motion: reduce) {
    transition: none;
  }

  &:empty::before {
    content: attr(data-placeholder);
    opacity: 0.35;
    font-style: italic;
  }
}

.edit-textarea {
  appearance: none;
  border: none;
  background: transparent;
  padding: 0;
  margin: 0;
  resize: none;
  // Textareas ignore flex stretch by default
  width: 100%;
  height: 100%;
  font: inherit;
  color: inherit;
  border-radius: var(--radius-xs);
  outline: $outline;
  outline-offset: var(--gap-sm);
  overflow-y: auto;
  scrollbar-width: none;
}
</style>
