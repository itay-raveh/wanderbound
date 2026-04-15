<script lang="ts" setup>
import LoginButtons from "@/components/register/LoginButtons.vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n();

defineProps<{
  authenticated: boolean;
  demoLoading: boolean;
}>();

const emit = defineEmits<{
  google: [credential: string];
  microsoft: [];
  demo: [];
}>();
</script>

<template>
  <q-btn
    v-if="authenticated"
    :label="t('landing.openEditor')"
    color="primary"
    unelevated
    no-caps
    size="lg"
    :to="{ name: 'editor' }"
  />
  <div v-else class="auth-actions column no-wrap items-center">
    <LoginButtons
      @google="(r) => emit('google', r.credential)"
      @microsoft="emit('microsoft')"
    />
    <button
      type="button"
      class="demo-btn"
      :disabled="demoLoading"
      @click="emit('demo')"
    >
      <q-spinner-dots v-if="demoLoading" size="1em" color="primary" />
      <template v-else>{{ t("demo.tryButton") }}</template>
    </button>
  </div>
</template>

<style scoped>
.auth-actions {
  gap: var(--gap-md-lg);
}

.demo-btn {
  all: unset;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16.25rem;
  height: 2.75rem;
  font-family: var(--font-ui);
  font-size: var(--type-sm);
  font-weight: 600;
  border-radius: var(--radius-full);
  cursor: pointer;
  color: var(--q-primary);
  background: transparent;
  border: 2px dashed color-mix(in srgb, var(--q-primary) 40%, transparent);
  transition:
    background var(--duration-fast),
    border-color var(--duration-fast);

  &:hover:not(:disabled) {
    background: color-mix(in srgb, var(--q-primary) 8%, transparent);
    border-color: var(--q-primary);
  }

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 0.125rem;
  }

  &:active:not(:disabled) {
    transform: scale(0.98);
  }
  &:disabled {
    opacity: 0.6;
    cursor: default;
  }
}

@media (prefers-reduced-motion: reduce) {
  .demo-btn {
    transition: none;
  }
}
</style>
