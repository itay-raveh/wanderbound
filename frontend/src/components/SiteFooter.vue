<script lang="ts" setup>
import { useI18n } from "vue-i18n";
import { getSettings } from "@/config";

const { t } = useI18n();

const settings = getSettings();
const year = new Date().getFullYear();

const hasMeta = !!(settings.AUTHOR_NAME || settings.APP_VERSION);
</script>

<template>
  <footer class="site-footer text-caption">
    <nav class="site-footer-group">
      <router-link to="/legal#privacy" class="site-footer-link">{{
        t("footer.privacy")
      }}</router-link>
      <span class="site-footer-sep" aria-hidden="true">&middot;</span>
      <router-link to="/legal#terms" class="site-footer-link">{{
        t("footer.terms")
      }}</router-link>
      <template v-if="settings.CONTACT_EMAIL || settings.GITHUB_URL">
        <span class="site-footer-sep" aria-hidden="true">&middot;</span>
        <a
          v-if="settings.CONTACT_EMAIL"
          :href="`mailto:${settings.CONTACT_EMAIL}`"
          class="site-footer-link"
        >
          {{ t("footer.contact") }} {{ settings.CONTACT_EMAIL }}
        </a>
        <span
          v-if="settings.CONTACT_EMAIL && settings.GITHUB_URL"
          class="site-footer-sep"
          aria-hidden="true"
          >&middot;</span
        >
        <a
          v-if="settings.GITHUB_URL"
          :href="settings.GITHUB_URL"
          target="_blank"
          rel="noopener"
          class="site-footer-link"
        >
          {{ t("footer.issues") }}
        </a>
      </template>
    </nav>
    <div v-if="hasMeta" class="site-footer-meta" dir="ltr">
      <span v-if="settings.AUTHOR_NAME">
        &copy; {{ year }}
        <a
          v-if="settings.AUTHOR_URL"
          :href="settings.AUTHOR_URL"
          target="_blank"
          rel="noopener"
          class="site-footer-link"
        >
          {{ settings.AUTHOR_NAME }}
        </a>
        <template v-else>{{ settings.AUTHOR_NAME }}</template>
      </span>
      <span
        v-if="settings.AUTHOR_NAME && settings.APP_VERSION"
        class="site-footer-sep"
        aria-hidden="true"
        >&middot;</span
      >
      <span v-if="settings.APP_VERSION">{{ settings.APP_VERSION }}</span>
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

.site-footer-meta {
  display: flex;
  align-items: center;
  gap: var(--gap-md);
  white-space: nowrap;
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
