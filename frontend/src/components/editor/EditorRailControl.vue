<script lang="ts" setup>
import {
  symOutlinedLeftPanelClose,
  symOutlinedLeftPanelOpen,
  symOutlinedRightPanelClose,
  symOutlinedRightPanelOpen,
} from "@quasar/extras/material-symbols-outlined";
import type { QBtn } from "quasar";
import { computed, ref } from "vue";

const props = defineProps<{
  side: "left" | "right";
  open: boolean;
  title: string;
  controls: string;
  showLabel: string;
  hideLabel: string;
}>();

const emit = defineEmits<{
  toggle: [];
}>();

const icon = computed(() => {
  if (props.side === "left") {
    return props.open ? symOutlinedLeftPanelClose : symOutlinedLeftPanelOpen;
  }
  return props.open ? symOutlinedRightPanelClose : symOutlinedRightPanelOpen;
});

const label = computed(() => (props.open ? props.hideLabel : props.showLabel));
const button = ref<QBtn | null>(null);

defineExpose({
  focus: () => button.value?.$el.focus(),
});
</script>

<template>
  <div
    v-if="open"
    class="editor-rail-control editor-rail-control--open"
    :class="`editor-rail-control--${side}`"
  >
    <span class="editor-rail-control__title">{{ title }}</span>
    <q-btn
      ref="button"
      flat
      dense
      round
      :icon="icon"
      :aria-label="label"
      :aria-controls="controls"
      :aria-expanded="open"
      @click="emit('toggle')"
    >
      <q-tooltip>{{ label }}</q-tooltip>
    </q-btn>
  </div>

  <q-btn
    ref="button"
    v-else
    flat
    dense
    class="editor-rail-control editor-rail-control--edge"
    :class="`editor-rail-control--${side}`"
    :icon="icon"
    :aria-label="label"
    :aria-controls="controls"
    :aria-expanded="open"
    @click="emit('toggle')"
  >
    <q-tooltip>{{ label }}</q-tooltip>
  </q-btn>
</template>

<style lang="scss" scoped>
.editor-rail-control {
  color: var(--text-muted);

  &:hover,
  &:focus-visible {
    color: var(--text-bright);
  }
}

.editor-rail-control--open {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 2.75rem;
  padding-inline: var(--gap-md-lg) var(--gap-sm);
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);

  &.editor-rail-control--right {
    flex-direction: row-reverse;
    padding-inline: var(--gap-sm) var(--gap-md-lg);
  }
}

.editor-rail-control__title {
  color: var(--text-muted);
  font-size: var(--type-xs);
  font-weight: 700;
  letter-spacing: var(--tracking-wide);
  text-transform: uppercase;
}

.editor-rail-control--edge {
  min-width: 2rem;
  min-height: 2.5rem;
  padding: 0;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);

  &.editor-rail-control--left {
    border-inline-start: 0;
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  }

  &.editor-rail-control--right {
    border-inline-end: 0;
    border-radius: var(--radius-sm) 0 0 var(--radius-sm);
  }
}
</style>
