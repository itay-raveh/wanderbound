<script lang="ts" setup>
import { useI18n } from "vue-i18n";
import RegisterStep from "./RegisterStep.vue";

const { t } = useI18n();
</script>

<template>
  <RegisterStep :number="1">
    <template #title>{{ t("register.getDataTitle") }}</template>
    <i18n-t
      keypath="register.getDataBody"
      tag="p"
      class="step-text text-body2 text-muted no-margin"
    >
      <template #link>
        <a href="https://www.polarsteps.com" target="_blank">polarsteps.com</a>
      </template>
      <template #settings>
        <strong>Account Settings</strong>
      </template>
      <template #download>
        <strong>Download my data</strong>
      </template>
      <template #startArchive>
        <strong>Start My Archive</strong>
      </template>
    </i18n-t>
  </RegisterStep>
</template>

<style scoped>
.step-text a {
  color: var(--q-primary);
  text-decoration: none;
  font-weight: 500;
}

.step-text a:hover {
  text-decoration: underline;
}

.step-text strong {
  color: var(--text);
  font-weight: 600;
}
</style>
