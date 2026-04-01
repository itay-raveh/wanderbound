<script lang="ts" setup>
import { useI18n } from "vue-i18n";
import { matOpenInNew } from "@quasar/extras/material-icons";

const { t } = useI18n();

const POLARSTEPS_GUIDE =
  "https://support.polarsteps.com/hc/en-us/articles/24266264821138-How-can-I-export-a-copy-of-my-data";
</script>

<template>
  <div class="instructions">
    <ol class="steps text-body2 text-muted">
      <li>
        <i18n-t keypath="register.getDataStep1">
          <template #link>
            <a href="https://www.polarsteps.com" target="_blank" rel="noopener">polarsteps.com</a>
          </template>
        </i18n-t>
      </li>
      <li>
        <i18n-t keypath="register.getDataStep2">
          <template #settings><strong>Account Settings</strong></template>
          <template #download><strong>Download my data</strong></template>
        </i18n-t>
      </li>
      <li>
        <i18n-t keypath="register.getDataStep3">
          <template #startArchive><strong>Start My Archive</strong></template>
        </i18n-t>
      </li>
      <li>{{ t("register.getDataStep4") }}</li>
    </ol>
    <p class="wait-note text-caption text-faint">{{ t("register.getDataWait") }}</p>
    <a :href="POLARSTEPS_GUIDE" target="_blank" rel="noopener" class="guide-link text-body2">
      {{ t("register.getDataGuide") }}
      <q-icon :name="matOpenInNew" size="0.75rem" />
    </a>
  </div>
</template>

<style scoped>
.steps {
  margin: 0;
  padding-inline-start: 1.5rem;
  line-height: 1.75;
}

.steps li + li {
  margin-top: var(--gap-xs);
}

.instructions a {
  color: var(--q-primary);
  text-decoration: none;
  font-weight: 500;
}

.instructions a:hover {
  text-decoration: underline;
}

.instructions a:focus-visible {
  outline: 0.125rem solid var(--q-primary);
  outline-offset: 0.125rem;
  border-radius: var(--radius-xs);
}

.instructions strong {
  color: var(--text);
  font-weight: 600;
}

.wait-note {
  margin: var(--gap-md) 0 0;
  line-height: 1.5;
}

.guide-link {
  display: inline-flex;
  align-items: center;
  gap: var(--gap-xs);
  margin-top: var(--gap-sm-md);
}
</style>
