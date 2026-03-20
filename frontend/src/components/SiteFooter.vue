<script lang="ts" setup>
import { useI18n } from "vue-i18n";

const { t } = useI18n();

const contactEmail = import.meta.env.VITE_CONTACT_EMAIL;
const githubUrl = import.meta.env.VITE_GITHUB_URL;
const authorName = import.meta.env.VITE_AUTHOR_NAME;
const authorUrl = import.meta.env.VITE_AUTHOR_URL;
const version = __APP_VERSION__ !== "0.0.0" ? __APP_VERSION__ : undefined;
const year = new Date().getFullYear();

const hasLinks = !!(contactEmail || githubUrl);
const hasMeta = !!(authorName || version);
const hasAny = hasLinks || hasMeta;
</script>

<template>
  <nav v-if="hasAny" class="site-footer text-caption">
    <div v-if="hasLinks" class="site-footer-group">
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
    </div>
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
  </nav>
</template>

<style scoped>
.site-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--gap-md);
  padding: var(--gap-md-lg) var(--gap-lg);
  border-top: 1px solid var(--border-color);
  color: var(--text-faint);
}

.site-footer-group {
  display: flex;
  align-items: center;
  gap: var(--gap-md);
}

.site-footer-link {
  color: var(--text-faint);
  text-decoration: none;
  transition: color var(--duration-fast);

  &:hover {
    color: var(--q-primary);
  }
}

.site-footer-sep {
  color: var(--border-color);
}
</style>
