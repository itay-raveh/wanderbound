<script lang="ts" setup>
import { useMeta } from "quasar";
import { marked } from "marked";
import privacyRaw from "../../../PRIVACY.md?raw";
import termsRaw from "../../../TERMS.md?raw";

useMeta({ title: "Legal" });

const privacyHtml = marked.parse(privacyRaw) as string;
const termsHtml = marked.parse(termsRaw) as string;
</script>

<template>
  <main class="legal-page" dir="ltr">
    <div id="privacy" class="legal-anchor" />
    <section class="legal-section prose" v-html="privacyHtml" />
    <hr class="legal-divider" />
    <div id="terms" class="legal-anchor" />
    <section class="legal-section prose" v-html="termsHtml" />
  </main>
</template>

<style scoped>
.legal-page {
  max-width: 48rem;
  margin: 0 auto;
  padding: 3rem 1.5rem;
}

.legal-anchor {
  scroll-margin-top: 1rem;
}

.legal-divider {
  margin: 3rem 0;
  border: none;
  border-top: 1px solid var(--border-color);
}

.prose :deep(h1) {
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--text-bright);
  margin: 0 0 0.5rem;
  letter-spacing: var(--tracking-tight);
}

.prose :deep(h2) {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-bright);
  margin: 2rem 0 0.75rem;
}

.prose :deep(h3) {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text);
  margin: 1.5rem 0 0.5rem;
}

.prose :deep(p) {
  color: var(--text-muted);
  line-height: 1.7;
  margin: 0.75rem 0;
}

.prose :deep(em:first-child) {
  color: var(--text-faint);
  font-size: var(--type-sm);
}

.prose :deep(ul) {
  color: var(--text-muted);
  line-height: 1.7;
  padding-left: 1.5rem;
  margin: 0.5rem 0;
}

.prose :deep(li) {
  margin: 0.25rem 0;
}

.prose :deep(strong) {
  color: var(--text);
  font-weight: 600;
}

.prose :deep(a) {
  color: var(--q-primary);
  text-decoration: none;
}

.prose :deep(a:hover) {
  text-decoration: underline;
}

.prose :deep(hr) {
  margin: 2rem 0;
  border: none;
  border-top: 1px solid var(--border-color);
}

.prose :deep(code) {
  font-family: var(--font-mono);
  font-size: var(--type-sm);
  background: var(--surface);
  padding: 0.125rem 0.375rem;
  border-radius: var(--radius-xs);
}
</style>
