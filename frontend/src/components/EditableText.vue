<script lang="ts" setup>
import { usePrintMode } from "@/composables/usePrintReady";
import { ref } from "vue";

const props = withDefaults(
  defineProps<{
    modelValue: string;
    displayValue?: string;
    multiline?: boolean;
    placeholder?: string;
  }>(),
  { multiline: false, placeholder: "" },
);

const emit = defineEmits<{
  "update:modelValue": [value: string];
}>();

const printMode = usePrintMode();

// --- Inline mode (single-line contenteditable) ---
const el = ref<HTMLElement | null>(null);
const editing = ref(false);

function commit() {
  editing.value = false;
  const text = (el.value?.innerText ?? "").trim();
  if (el.value) el.value.textContent = text;
  if (text !== props.modelValue) {
    emit("update:modelValue", text);
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") {
    if (el.value) el.value.textContent = props.modelValue;
    editing.value = false;
    (e.target as HTMLElement).blur();
  } else if (e.key === "Enter") {
    e.preventDefault();
    (e.target as HTMLElement).blur();
  }
}

// --- Modal mode (multiline dialog) ---
const dialogOpen = ref(false);
const draft = ref("");

function saveDialog() {
  const text = draft.value.replace(/\r\n/g, "\n").replace(/^\n+|\n+$/g, "");
  if (text !== props.modelValue) {
    emit("update:modelValue", text);
  }
  dialogOpen.value = false;
}
</script>

<template>
  <!-- Print mode: plain text, no editing affordances -->
  <div v-if="printMode">{{ displayValue ?? modelValue }}</div>

  <!-- Multiline: styled div that opens a modal -->
  <div
    v-else-if="multiline"
    class="editable-text"
    :data-placeholder="placeholder"
    @click="dialogOpen = true"
  >
    {{ displayValue ?? modelValue }}

    <q-dialog v-model="dialogOpen" @before-show="draft = modelValue">
      <q-card class="desc-dialog column no-wrap">
        <q-card-section class="text-h6">Edit description</q-card-section>
        <q-card-section class="col scroll">
          <q-input
            v-model="draft"
            type="textarea"
            outlined
            dir="auto"
            class="fit"
            input-class="desc-textarea"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat label="Cancel" @click="dialogOpen = false" />
          <q-btn flat label="Save" color="primary" @click="saveDialog" />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </div>

  <!-- Single-line: inline contenteditable -->
  <div
    v-else
    ref="el"
    class="editable-text"
    contenteditable="plaintext-only"
    :data-placeholder="placeholder"
    :spellcheck="editing"
    @focus="editing = true"
    @blur="commit"
    @keydown="onKeydown"
  >{{ modelValue }}</div>
</template>

<style lang="scss" scoped>
.editable-text {
  cursor: text;
  border-radius: var(--radius-xs);
  box-decoration-break: clone;
  outline: 2px dashed color-mix(in srgb, currentColor 35%, transparent);
  outline-offset: 0.25rem;
  transition:
    outline-color var(--duration-fast) ease,
    background-color var(--duration-fast) ease;

  &:hover {
    outline-color: color-mix(in srgb, currentColor 55%, transparent);
  }

  &:empty::before {
    content: attr(data-placeholder);
    opacity: 0.35;
    font-style: italic;
  }
}

.desc-dialog {
  width: 40rem;
  max-width: 90vw;
  height: 70vh;
  max-height: 70vh;
}

:deep(.desc-textarea) {
  height: 100% !important;
  resize: none;
}

:deep(.q-field__inner),
:deep(.q-field__control) {
  height: 100%;
}
</style>
