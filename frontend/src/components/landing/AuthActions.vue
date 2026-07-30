<script lang="ts" setup>
import LoginButtons from "@/components/register/LoginButtons.vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n();

defineProps<{
  authenticated: boolean;
  demoLoading: boolean;
  localLoginEnabled: boolean;
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
    <i18n-t keypath="landing.selfHostPrompt" tag="p" class="self-host-prompt">
      <template #link>
        <a
          href="https://github.com/itay-raveh/wanderbound#self-hosting"
          target="_blank"
          rel="noopener"
          class="self-host-link"
        >
          {{ t("landing.selfHostLink") }}
        </a>
      </template>
    </i18n-t>
    <q-btn
      v-if="localLoginEnabled"
      data-test="local-login"
      :label="t('login.localZip')"
      color="primary"
      unelevated
      no-caps
      size="lg"
      :to="{ name: 'upload' }"
    />
    <LoginButtons
      v-else
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

.self-host-prompt {
  margin: 0;
  color: var(--text-muted);
  font-size: var(--type-sm);
  text-align: center;
}

.self-host-link {
  color: inherit;
  font-weight: 600;
  text-underline-offset: 0.15em;
  transition: color var(--duration-fast);

  &:hover {
    color: var(--q-primary);
  }

  &:focus-visible {
    border-radius: var(--radius-xs);
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 0.125rem;
  }
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
