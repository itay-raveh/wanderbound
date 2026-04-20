<script lang="ts" setup>
import { useId } from "vue";

const show = defineModel<boolean>({ required: true });

const id = useId();

withDefaults(
  defineProps<{
    icon: string;
    variant?: "danger" | "warning" | "primary";
    title: string;
    body: string;
    tip?: string;
    confirmLabel?: string;
    cancelLabel: string;
    confirmDisabled?: boolean;
    secondaryLabel?: string;
  }>(),
  { variant: "danger" },
);

defineEmits<{
  confirm: [];
  secondary: [];
}>();
</script>

<template>
  <q-dialog
    v-model="show"
    :aria-labelledby="`${id}-title`"
    :aria-describedby="body ? `${id}-body` : undefined"
  >
    <q-card class="prompt-dialog text-center">
      <div :class="['prompt-icon flex flex-center', variant]">
        <q-icon :name="icon" size="1.5rem" />
      </div>
      <h3 :id="`${id}-title`" class="prompt-title text-weight-semibold text-bright">
        {{ title }}
      </h3>
      <p v-if="body" :id="`${id}-body`" class="prompt-text text-body2 text-muted">{{ body }}</p>
      <p v-if="tip" class="prompt-tip text-body2 text-faint">{{ tip }}</p>
      <div class="prompt-actions">
        <q-btn v-close-popup flat no-caps class="text-body2 cancel-btn">{{
          cancelLabel
        }}</q-btn>
        <q-btn
          v-if="secondaryLabel"
          flat
          no-caps
          :class="[
            'text-body2',
            confirmLabel ? 'secondary-btn' : 'confirm-btn primary',
          ]"
          @click="$emit('secondary')"
        >
          {{ secondaryLabel }}
        </q-btn>
        <q-btn
          v-if="confirmLabel"
          flat
          no-caps
          :disable="confirmDisabled"
          :class="['text-body2 confirm-btn', variant]"
          @click="$emit('confirm')"
        >
          {{ confirmLabel }}
        </q-btn>
      </div>
    </q-card>
  </q-dialog>
</template>

<style lang="scss" scoped>
.prompt-dialog {
  padding: 1.75rem;
  max-width: 26rem;
}

.prompt-icon {
  width: 2.75rem;
  height: 2.75rem;
  border-radius: 50%;
  margin: 0 auto var(--gap-lg);

  &.danger {
    background: color-mix(in srgb, var(--danger) 15%, var(--surface));
    color: var(--danger);
  }

  &.warning {
    background: color-mix(in srgb, var(--q-warning) 15%, var(--surface));
    color: var(--q-warning);
  }

  &.primary {
    background: color-mix(in srgb, var(--q-primary) 15%, var(--surface));
    color: var(--q-primary);
  }
}

.prompt-title {
  font-size: var(--type-subtitle);
  margin: 0 0 var(--gap-md);
}

.prompt-text {
  line-height: 1.5;
  white-space: pre-line;
  margin: 0 0 var(--gap-lg);
}

.prompt-tip {
  font-size: var(--type-xs);
  margin: calc(var(--gap-lg) * -1) 0 var(--gap-lg);
}

.prompt-actions {
  display: flex;
  gap: var(--gap-md);

  > .q-btn {
    flex: 1 1 auto;
  }
}

.cancel-btn {
  background: var(--surface);
  border: 1px solid var(--border-color);
}

.secondary-btn {
  border: 1px solid var(--border-color);
}

.confirm-btn {
  &.danger {
    background: var(--danger);
    color: var(--text-on-color);
  }

  &.warning {
    background: var(--q-warning);
    color: var(--text-on-warning);
  }

  &.primary {
    background: var(--q-primary);
    color: var(--text-on-color);
  }
}
</style>
