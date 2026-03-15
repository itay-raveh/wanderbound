<script lang="ts" setup>
import { symOutlinedEdit } from "@quasar/extras/material-symbols-outlined";
import { ref } from "vue";

const props = defineProps<{
  modelValue: string;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: string];
}>();

const el = ref<HTMLElement | null>(null);
const editing = ref(false);

function commit() {
  editing.value = false;
  const text = el.value?.textContent?.trim() ?? "";
  if (el.value) el.value.textContent = text;
  if (text !== props.modelValue) {
    emit("update:modelValue", text);
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === "Enter") {
    e.preventDefault();
    (e.target as HTMLElement).blur();
  } else if (e.key === "Escape") {
    if (el.value) el.value.textContent = props.modelValue;
    editing.value = false;
    (e.target as HTMLElement).blur();
  }
}

function onPaste(e: ClipboardEvent) {
  e.preventDefault();
  const text = e.clipboardData?.getData("text/plain") ?? "";
  document.execCommand("insertText", false, text);
}
</script>

<template>
  <div class="editable-text">
    <div
      ref="el"
      class="editable-text__input"
      contenteditable="true"
      :spellcheck="editing"
      @focus="editing = true"
      @blur="commit"
      @keydown="onKeydown"
      @paste="onPaste"
    ><slot /></div>
    <span class="editable-text__badge" @mousedown.prevent>
      <q-icon :name="symOutlinedEdit" size="0.55rem" />
    </span>
  </div>
</template>

<style lang="scss" scoped>
.editable-text {
  position: relative;
  display: inline-block;
}

.editable-text__input {
  cursor: text;
  outline: 3px dashed rgba(255, 255, 255, 0.35);
  outline-offset: 0.3rem;
  border-radius: 0.25rem;
  transition:
    outline-color 0.2s ease,
    background-color 0.2s ease;

  &:hover:not(:focus) {
    outline-color: rgba(255, 255, 255, 0.55);
  }

  &:focus {
    outline-color: rgba(255, 255, 255, 0.7);
    outline-style: solid;
    background: rgba(255, 255, 255, 0.08);
  }
}

.editable-text__badge {
  position: absolute;
  top: -0.75rem;
  right: -0.75rem;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.125rem;
  height: 1.125rem;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.9);
  color: rgba(0, 0, 0, 0.65);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
  pointer-events: none;
}
</style>
