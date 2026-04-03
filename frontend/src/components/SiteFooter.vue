<script lang="ts" setup>
import { useI18n } from "vue-i18n";

const { t } = useI18n();

const contactEmail = import.meta.env.VITE_CONTACT_EMAIL;
const githubUrl = import.meta.env.VITE_GITHUB_URL;
const authorName = import.meta.env.VITE_AUTHOR_NAME;
const authorUrl = import.meta.env.VITE_AUTHOR_URL;
const version = __APP_VERSION__ !== "0.0.0" ? __APP_VERSION__ : undefined;
const year = new Date().getFullYear();

const hasMeta = !!(authorName || version);
</script>

<template>
  <footer class="site-footer text-caption">
    <nav class="site-footer-group">
      <router-link to="/legal#privacy" class="site-footer-link">{{ t("footer.privacy") }}</router-link>
      <span class="site-footer-sep" aria-hidden="true">&middot;</span>
      <router-link to="/legal#terms" class="site-footer-link">{{ t("footer.terms") }}</router-link>
      <template v-if="contactEmail || githubUrl">
        <span class="site-footer-sep" aria-hidden="true">&middot;</span>
        <a
          v-if="contactEmail"
          :href="`mailto:${contactEmail}`"
          class="site-footer-link"
        >
          {{ t("footer.contact") }} {{ contactEmail }}
        </a>
        <span
          v-if="contactEmail && githubUrl"
          class="site-footer-sep"
          aria-hidden="true"
          >&middot;</span
        >
        <a
          v-if="githubUrl"
          :href="githubUrl"
          target="_blank"
          rel="noopener"
          class="site-footer-link"
        >
          {{ t("footer.issues") }}
        </a>
      </template>
    </nav>
    <div v-if="hasMeta" class="site-footer-group">
      <span v-if="authorName" dir="ltr">
        &copy; {{ year }}
        <a
          v-if="authorUrl"
          :href="authorUrl"
          target="_blank"
          rel="noopener"
          class="site-footer-link"
        >
          {{ authorName }}
        </a>
        <template v-else>{{ authorName }}</template>
      </span>
      <span
        v-if="authorName && version"
        class="site-footer-sep"
        aria-hidden="true"
        >&middot;</span
      >
      <span v-if="version">v{{ version }}</span>
    </div>
    <p class="site-footer-disclaimer">
      {{ t("footer.disclaimerIndependent") }}<br />
      {{ t("footer.disclaimerRecommendation") }}
    </p>
  </footer>
</template>

<style scoped>
.site-footer {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--gap-sm);
  padding: var(--gap-lg) var(--gap-lg) var(--gap-md-lg);
  border-top: 1px solid var(--border-color);
  background: var(--bg-secondary);
  color: var(--text-muted);
}

.site-footer-group {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--gap-sm) var(--gap-md);
}

.site-footer-link {
  color: var(--text-muted);
  text-decoration: none;
  padding: var(--gap-sm-md) var(--gap-md);
  margin: calc(-1 * var(--gap-sm-md)) calc(-1 * var(--gap-md));
  transition: color var(--duration-fast);

  &:hover {
    color: var(--q-primary);
  }
}

.site-footer-sep {
  color: var(--border-color);
}

@media (prefers-reduced-motion: reduce) {
  .site-footer-link {
    transition: none;
  }
}

.site-footer-disclaimer {
  margin: var(--gap-sm) 0 0;
  max-width: 52rem;
  text-align: center;
  color: var(--text-muted);
  line-height: 1.5;
}
</style>
