<script lang="ts" setup>
import { authGoogle, authMicrosoft, readUser } from "@/client";
import { microsoftLogin } from "@/composables/useMicrosoftAuth";
import LoginButtons from "@/components/register/LoginButtons.vue";
import { useQuasar } from "quasar";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { onMounted, ref } from "vue";
import { type CallbackTypes } from "vue3-google-login";
import { setAuthState, type Provider } from "@/router";

const { t } = useI18n();
const router = useRouter();
const $q = useQuasar();

const authenticated = ref(false);

onMounted(async () => {
  try {
    await readUser();
    authenticated.value = true;
  } catch {
    /* not logged in */
  }
});

const features = [
  { key: "autoAlbum", image: "/landing/auto-album.jpg" },
  { key: "hikeMap", image: "/landing/hike-map.jpg" },
  { key: "videoPoster", image: "/landing/video-poster.jpg" },
  { key: "localization", image: "/landing/localization.jpg" },
] as const;

const AUTH_FNS = { google: authGoogle, microsoft: authMicrosoft } as const satisfies Record<Provider, unknown>;

async function handleLogin(credential: string, provider: Provider) {
  const { data: user } = await AUTH_FNS[provider]({ body: { credential } });
  if (user) {
    await router.push({ name: "editor" });
  } else {
    setAuthState(credential, provider);
    await router.push({ name: "upload" });
  }
}

function notifyLoginFailed() {
  $q.notify({ type: "negative", message: t("login.signInFailed") });
}

function onGoogleSuccess(response: CallbackTypes.CredentialPopupResponse) {
  void handleLogin(response.credential, "google").catch(notifyLoginFailed);
}

async function onMicrosoftLogin() {
  try {
    const idToken = await microsoftLogin();
    await handleLogin(idToken, "microsoft");
  } catch {
    notifyLoginFailed();
  }
}
</script>

<template>
  <main>
    <!-- Hero -->
    <section class="hero">
      <div class="hero-content column no-wrap items-center">
        <q-img src="/logo.svg" class="hero-logo fade-up" />
        <h1 class="hero-title fade-up">{{ t("brand") }}</h1>
        <p class="hero-tagline fade-up">{{ t("tagline") }}</p>
        <div class="hero-cta fade-up">
          <q-btn
            v-if="authenticated"
            :label="t('landing.openEditor')"
            color="primary"
            unelevated
            no-caps
            size="lg"
            :to="{ name: 'editor' }"
          />
          <LoginButtons v-else @google="onGoogleSuccess" @microsoft="onMicrosoftLogin" />
        </div>
      </div>

      <!-- Hero showcase: product preview that overflows into the features section -->
      <div class="hero-showcase fade-up">
        <img
          src="/landing/editor.jpg"
          :alt="t('landing.editorScreenshot')"
          class="hero-screenshot"
        />
      </div>
    </section>

    <!-- Features -->
    <section class="features">
      <div
        v-for="(f, i) in features"
        :key="f.key"
        class="feature"
        :class="{ reverse: i % 2 === 1 }"
      >
        <img
          :src="f.image"
          :alt="t(`landing.${f.key}Title`)"
          class="feature-img"
          loading="lazy"
        />
        <div class="feature-text">
          <h2 class="feature-title">{{ t(`landing.${f.key}Title`) }}</h2>
          <p class="feature-body">{{ t(`landing.${f.key}Body`) }}</p>
        </div>
      </div>
    </section>

    <!-- Bottom CTA -->
    <section class="cta column no-wrap flex-center">
      <h2 class="cta-title">{{ t("landing.ctaTitle") }}</h2>
      <p class="cta-subtitle">{{ t("landing.ctaBody") }}</p>
      <div class="cta-button">
        <q-btn
          v-if="authenticated"
          :label="t('landing.openEditor')"
          color="primary"
          unelevated
          no-caps
          size="lg"
          :to="{ name: 'editor' }"
        />
        <LoginButtons v-else @google="onGoogleSuccess" @microsoft="onMicrosoftLogin" />
      </div>
    </section>
  </main>
</template>

<style scoped>
/* Hero */
.hero {
  background: var(--page-gradient);
  text-align: center;
  overflow: hidden;
}

.hero-content {
  padding: 2.5rem 1.5rem 0;
}

.hero-logo {
  width: 3.5rem;
  height: 3.5rem;
}

.hero-title {
  margin: 0.75rem 0 0;
  font-size: 1.5rem;
  font-weight: 800;
  color: var(--text-bright);
  letter-spacing: var(--tracking-tight);
}

.hero-tagline {
  margin: 0.5rem 0 0;
  font-size: var(--type-md);
  color: var(--text-muted);
  max-width: 32rem;
}

.hero-cta {
  margin-top: 1.5rem;
  animation-delay: 0.1s;
}

/* Product preview in hero */
.hero-showcase {
  margin-top: 2rem;
  padding: 0 0.5rem;
  animation-delay: 0.15s;
}

.hero-screenshot {
  display: block;
  width: 100%;
  max-width: 64rem;
  margin: 0 auto;
  border-radius: var(--radius-xl) var(--radius-xl) 0 0;
  box-shadow:
    0 -4px 32px rgba(0, 0, 0, 0.08),
    0 -1px 0 rgba(255, 255, 255, 0.06) inset;
}

/* Features */
.features {
  background: var(--bg);
  padding: 3rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 3rem;
}

.feature {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1.25rem;
  max-width: 64rem;
  margin: 0 auto;
  width: 100%;
  align-items: center;
}

.feature-img {
  width: 100%;
  border-radius: var(--radius-lg);
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.12);
}

.feature-title {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-bright);
  letter-spacing: var(--tracking-tight);
}

.feature-body {
  margin: 0.75rem 0 0;
  font-size: var(--type-md);
  color: var(--text-muted);
  line-height: 1.65;
}

/* Bottom CTA */
.cta {
  background: var(--bg-deep);
  padding: 3rem 1.5rem;
  text-align: center;
}

.cta-title {
  margin: 0;
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--text-bright);
}

.cta-subtitle {
  margin: 0.75rem 0 0;
  font-size: var(--type-md);
  color: var(--text-muted);
  max-width: 28rem;
}

.cta-button {
  margin-top: 2rem;
}

/* Desktop */
@media (min-width: 768px) {
  .hero-content {
    padding: 5rem 2rem 0;
  }

  .hero-logo {
    width: 6rem;
    height: 6rem;
  }

  .hero-title {
    font-size: var(--display-2);
    margin: 1.25rem 0 0;
  }

  .hero-tagline {
    font-size: var(--type-xl);
  }

  .hero-cta {
    margin-top: 2rem;
  }

  .hero-showcase {
    margin-top: 4rem;
    padding: 0 3rem;
  }

  .features {
    padding: 5rem 1.5rem;
    gap: 4rem;
  }

  .feature {
    grid-template-columns: 1fr 1fr;
    gap: 2rem;
  }

  .cta {
    padding: 5rem 2rem;
  }

  .feature.reverse .feature-img {
    order: 2;
  }

  .feature.reverse .feature-text {
    order: 1;
  }
}
</style>
