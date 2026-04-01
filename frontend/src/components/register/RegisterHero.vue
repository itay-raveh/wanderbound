<script lang="ts" setup>
import { useI18n } from "vue-i18n";

defineProps<{
  userName?: string;
}>();

const { t } = useI18n();
</script>

<template>
  <header class="hero fade-up column no-wrap items-center">
    <img src="/logo.svg" alt="Wanderbound" class="hero-logo" />
    <div class="hero-text column no-wrap items-center">
      <h1 v-if="userName" class="text-h6 text-bright no-margin">{{ t("register.greeting", { name: userName }) }}</h1>
      <h1 v-else class="text-h6 text-bright no-margin">{{ t("register.welcomeNew") }}</h1>
      <span class="text-subtitle2 text-faint">
        {{ userName ? t("register.welcomeBack") : t("tagline") }}
      </span>
    </div>
  </header>
</template>

<style scoped>
.hero {
  padding-bottom: var(--gap-lg);
  gap: var(--gap-md-lg);
  text-align: center;
}

.hero-logo {
  width: 3rem;
  height: 3rem;
  flex-shrink: 0;
}

.hero-text {
  gap: var(--gap-xs);
}

@media (max-width: 479px) {
  .hero-logo {
    width: 2.5rem;
    height: 2.5rem;
  }
}
</style>
