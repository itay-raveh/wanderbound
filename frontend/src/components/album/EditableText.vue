<script lang="ts" setup>
import type { TextPage } from "@/composables/useTextLayout";
import { usePrintMode } from "@/composables/usePrintReady";
import { ref, nextTick, onBeforeUnmount } from "vue";

const props = withDefaults(
  defineProps<{
    modelValue: string;
    multiline?: boolean;
    placeholder?: string;
    page?: TextPage;
  }>(),
  { multiline: false, placeholder: "" },
);

const emit = defineEmits<{
  "update:modelValue": [value: string];
}>();

const printMode = usePrintMode();
const editing = ref(false);
const draft = ref("");
const editEl = ref<HTMLTextAreaElement | HTMLElement | null>(null);

function startEdit() {
  if (editing.value) return;
  draft.value = props.modelValue;
  editing.value = true;
  void nextTick(() => {
    const el = editEl.value;
    if (el instanceof HTMLTextAreaElement) {
      const offset = props.page?.offset ?? 0;
      el.setSelectionRange(offset, offset);
      // Allow a short final page to start at its own first line.
      if (offset > 0) el.style.paddingBottom = `${el.clientHeight}px`;
      el.scrollTop =
        (props.page?.lineIndex ?? 0) *
        parseFloat(getComputedStyle(el).lineHeight);
    }
    el?.focus({ preventScroll: true });
  });
}

function commit() {
  const el = editEl.value;
  if (!editing.value || !el) return;
  editing.value = false;
  const raw = el instanceof HTMLTextAreaElement ? el.value : el.innerText;
  const text = props.multiline ? raw.replace(/\r\n?/g, "\n") : raw.trim();
  if (text !== props.modelValue) emit("update:modelValue", text);
}

// Virtualized pages can unmount before blur saves the edit.
onBeforeUnmount(commit);

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
  <div
    v-if="printMode"
    :dir="multiline ? (page?.direction ?? 'auto') : undefined"
  >
    {{ page?.text ?? modelValue }}
  </div>

  <!-- Keep the page's geometry and margins outside the scrolling textarea. -->
  <div
    v-else-if="multiline"
    :dir="page?.direction ?? 'auto'"
    :role="editing ? undefined : 'button'"
    :tabindex="editing ? undefined : 0"
    class="editable-display"
    :data-placeholder="placeholder"
    @click="startEdit"
    @keydown.enter.self.prevent="startEdit"
    @keydown.space.self.prevent="startEdit"
  >
    <textarea
      v-if="editing"
      ref="editEl"
      v-model="draft"
      dir="auto"
      class="edit-textarea"
      :placeholder="placeholder"
      :aria-label="placeholder || undefined"
      @blur="commit"
      @keydown="onKeydown"
    />
    <template v-else>{{ page?.text ?? modelValue }}</template>
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
  >
    {{ modelValue }}
  </div>
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
  display: block;
  box-sizing: border-box;
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
  outline: none;
  overflow-y: auto;
  scrollbar-width: none;
  white-space: pre-wrap;
  // Match the display's direction instead of textarea's per-paragraph default.
  unicode-bidi: isolate;
  overflow-wrap: break-word;
  tab-size: 8;
  text-align: start;
  hyphens: none;
}
</style>
