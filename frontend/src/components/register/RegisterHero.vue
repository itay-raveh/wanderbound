<script lang="ts" setup>
import { computed } from "vue";
import { useI18n } from "vue-i18n";

defineProps<{
  userName?: string;
}>();

const { t } = useI18n();

const greetingKey = computed(() => {
  const hour = new Date().getHours();
  if (hour < 12) return "register.greetingMorning";
  if (hour < 17) return "register.greetingAfternoon";
  return "register.greetingEvening";
});
</script>

<template>
  <header class="hero fade-up row no-wrap items-center justify-center q-gutter-x-md">
    <img src="/logo.svg" alt="" class="hero-logo" />
    <div class="hero-text column no-wrap justify-center">
      <span v-if="userName" class="text-h6 text-bright">{{ t(greetingKey, { name: userName }) }}</span>
      <span v-else class="text-h6 text-bright">{{ t("register.welcomeNew") }}</span>
      <span class="text-subtitle2 text-faint">
        {{ userName ? t("register.welcomeBack") : t("tagline") }}
      </span>
    </div>
  </header>
</template>

<style scoped>
.hero {
  padding-bottom: var(--gap-lg);
}

.hero-logo {
  width: 3rem;
  height: 3rem;
  flex-shrink: 0;
}

@media (max-width: 479px) {
  .hero-logo {
    width: 2.5rem;
    height: 2.5rem;
  }
}
</style>
