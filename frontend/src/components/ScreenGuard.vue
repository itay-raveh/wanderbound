<script lang="ts" setup>
import { computed } from "vue";
import { useRoute } from "vue-router";
import { useQuasar } from "quasar";
import { useI18n } from "vue-i18n";

const $q = useQuasar();
const route = useRoute();
const { t } = useI18n();

const screenTooSmall = computed(
  () => $q.screen.lt.md && route.name !== "print",
);
</script>

<template>
  <div v-if="screenTooSmall" class="gate flex flex-center">
    <div class="gate-content column no-wrap items-center q-gutter-y-md">
      <q-img src="/logo.svg" class="gate-logo" />
      <h1 class="text-h5 text-bright text-center no-margin">{{ t("screen.title") }}</h1>
      <p class="text-body1 text-muted text-center no-margin">{{ t("screen.body") }}</p>
    </div>
  </div>
  <slot v-else />
</template>

<style scoped>
.gate {
  min-height: 100vh;
  padding: 2rem;
  background: linear-gradient(
    to bottom,
    color-mix(in srgb, var(--q-primary) 8%, var(--bg-deep)),
    var(--bg)
  );
}

.gate-logo {
  width: 5rem;
  height: 5rem;
}

.gate-content {
  max-width: 24rem;
}
</style>
