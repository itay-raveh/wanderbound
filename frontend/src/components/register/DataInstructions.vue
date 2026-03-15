<script lang="ts" setup>
import RegisterStep from "./RegisterStep.vue";
</script>

<template>
  <RegisterStep :number="1">
    <template #title>Get your data from Polarsteps</template>
    <p class="step-text text-body2">
      Log in at
      <a href="https://www.polarsteps.com" target="_blank">polarsteps.com</a>
      on a desktop computer. Go to
      <strong>Account&nbsp;Settings</strong>, scroll to
      <strong>Download&nbsp;my&nbsp;data</strong> in the privacy section, and
      click <strong>Start My Archive</strong>. You'll receive an email with a
      download link.
    </p>
  </RegisterStep>
</template>

<style scoped>
.step-text {
  line-height: 1.6;
  color: var(--text-muted);
  margin: 0;
}

.step-text a {
  color: var(--accent-light);
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
