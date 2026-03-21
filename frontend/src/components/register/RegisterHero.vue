<script lang="ts" setup>
import { useI18n } from "vue-i18n";

const { t } = useI18n();
</script>

<template>
  <header class="hero fade-up row no-wrap items-center justify-center q-gutter-x-md">
    <q-img src="/logo.svg" class="hero-logo" />
    <div class="hero-text column no-wrap justify-center">
      <span class="text-h5 text-bright">{{ t("brand") }}</span>
      <span class="text-subtitle2 text-faint">
        {{ t("tagline") }}
      </span>
    </div>
  </header>
</template>

<style scoped>
.hero {
  padding-bottom: 2.5rem;
}

.hero-logo {
  width: 5rem;
  height: 5rem;
  flex-shrink: 0;
}
</style>
