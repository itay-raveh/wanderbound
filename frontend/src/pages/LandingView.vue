<script lang="ts" setup>
import { authGoogle, authMicrosoft, readUser } from "@/client";
import { microsoftLogin } from "@/composables/useMicrosoftAuth";
import LoginButtons from "@/components/register/LoginButtons.vue";
import { useQuasar } from "quasar";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { computed, onMounted, ref } from "vue";
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

const mode = computed(() => ($q.dark.isActive ? "dark" : "light"));

const WIDTHS = [640, 1024, 1536];

function srcset(stem: string) {
  const set = WIDTHS.map((w) => `/landing/${stem}-${mode.value}-${w}w.webp ${w}w`);
  set.push(`/landing/${stem}-${mode.value}.webp 2400w`);
  return set.join(", ");
}

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
    <section class="hero" aria-labelledby="hero-heading">
      <div class="hero-content column no-wrap items-center">
        <img src="/logo.svg" alt="" class="hero-logo fade-up" />
        <h1 id="hero-heading" class="hero-title fade-up">{{ t("brand") }}</h1>
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

      <!-- Hero showcase: fanned spread of different album page types -->
      <div class="hero-showcase fade-up">
        <div class="hero-fan">
          <picture class="hero-card" tabindex="0">
            <source :srcset="srcset('cover')" sizes="320px" type="image/webp" />
            <img :src="`/landing/cover-${mode}.jpg`" alt="" class="hero-card-img" />
          </picture>
          <picture class="hero-card" tabindex="0">
            <source :srcset="srcset('hike-map')" sizes="320px" type="image/webp" />
            <img :src="`/landing/hike-map-${mode}.jpg`" alt="" class="hero-card-img" />
          </picture>
          <picture class="hero-card" tabindex="0">
            <source :srcset="srcset('step-page')" sizes="320px" type="image/webp" />
            <img :src="`/landing/step-page-${mode}.jpg`" :alt="t('landing.heroScreenshot')" class="hero-card-img" fetchpriority="high" />
          </picture>
          <picture class="hero-card" tabindex="0">
            <source :srcset="srcset('overview')" sizes="320px" type="image/webp" />
            <img :src="`/landing/overview-${mode}.jpg`" alt="" class="hero-card-img" />
          </picture>
          <picture class="hero-card" tabindex="0">
            <source :srcset="srcset('auto-album')" sizes="320px" type="image/webp" />
            <img :src="`/landing/auto-album-${mode}.jpg`" alt="" class="hero-card-img" />
          </picture>
        </div>
      </div>

      <!-- Scroll hint — fades out as user scrolls -->
      <div class="hero-scroll-hint fade-up" aria-hidden="true">
        <svg width="20" height="10" viewBox="0 0 20 10" fill="none">
          <path d="M1 1l9 8 9-8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </div>
    </section>

    <!-- Feature: autoAlbum — core product showcase, standard 50/50 -->
    <section class="band band--default" aria-labelledby="auto-album-heading">
      <div class="feature feature--standard">
        <picture class="feature-picture">
          <source :srcset="srcset('auto-album')" sizes="(min-width: 1024px) 480px, 100vw" type="image/webp" />
          <img :src="`/landing/auto-album-${mode}.jpg`" :alt="t('landing.autoAlbumTitle')" class="feature-img" loading="lazy" />
        </picture>
        <div class="feature-text">
          <h2 id="auto-album-heading" class="feature-title">{{ t("landing.autoAlbumTitle") }}</h2>
          <p class="feature-body">{{ t("landing.autoAlbumBody") }}</p>
        </div>
      </div>
    </section>

    <!-- Feature: hikeMap — visually stunning, full-width breakout -->
    <section class="band band--showstopper" aria-labelledby="hike-map-heading">
      <div class="feature feature--hero">
        <div class="feature-text text-center">
          <h2 id="hike-map-heading" class="feature-title feature-title--lg">{{ t("landing.hikeMapTitle") }}</h2>
          <p class="feature-body">{{ t("landing.hikeMapBody") }}</p>
        </div>
        <picture class="feature-picture feature-picture--wide">
          <source :srcset="srcset('hike-map')" sizes="(min-width: 1024px) 960px, 100vw" type="image/webp" />
          <img :src="`/landing/hike-map-${mode}.jpg`" :alt="t('landing.hikeMapTitle')" class="feature-img" loading="lazy" />
        </picture>
      </div>
    </section>

    <!-- Features: stepPage + overview — data richness pair -->
    <section class="band band--default" aria-labelledby="step-page-heading overview-heading">
      <div class="feature-pair">
        <div class="feature-pair-item">
          <picture class="feature-picture">
            <source :srcset="srcset('step-page')" sizes="(min-width: 1024px) 480px, 100vw" type="image/webp" />
            <img :src="`/landing/step-page-${mode}.jpg`" :alt="t('landing.stepPageTitle')" class="feature-img" loading="lazy" />
          </picture>
          <h2 id="step-page-heading" class="feature-title">{{ t("landing.stepPageTitle") }}</h2>
          <p class="feature-body">{{ t("landing.stepPageBody") }}</p>
        </div>
        <div class="feature-pair-item">
          <picture class="feature-picture">
            <source :srcset="srcset('overview')" sizes="(min-width: 1024px) 480px, 100vw" type="image/webp" />
            <img :src="`/landing/overview-${mode}.jpg`" :alt="t('landing.overviewTitle')" class="feature-img" loading="lazy" />
          </picture>
          <h2 id="overview-heading" class="feature-title">{{ t("landing.overviewTitle") }}</h2>
          <p class="feature-body">{{ t("landing.overviewBody") }}</p>
        </div>
      </div>
    </section>

    <!-- Feature: localization — supporting detail, compact centered -->
    <section class="band band--accent" aria-labelledby="localization-heading">
      <div class="feature feature--compact">
        <picture class="feature-picture">
          <source :srcset="srcset('localization')" sizes="(min-width: 1024px) 480px, 100vw" type="image/webp" />
          <img :src="`/landing/localization-${mode}.jpg`" :alt="t('landing.localizationTitle')" class="feature-img" loading="lazy" />
        </picture>
        <div class="feature-text">
          <h2 id="localization-heading" class="feature-title">{{ t("landing.localizationTitle") }}</h2>
          <p class="feature-body">{{ t("landing.localizationBody") }}</p>
        </div>
      </div>
    </section>

    <!-- Bottom CTA -->
    <section class="cta column no-wrap flex-center" aria-labelledby="cta-heading">
      <h2 id="cta-heading" class="cta-title">{{ t("landing.ctaTitle") }}</h2>
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
/* Hero — tight vertical stack so everything fits above the fold */
.hero {
  background: var(--page-gradient);
  text-align: center;
  overflow: hidden;
  padding-bottom: 1.5rem;
}

.hero-content {
  padding: 2rem 1.5rem 0;
}

.hero-logo {
  width: 3rem;
  height: 3rem;
  transition: transform var(--duration-normal) ease;
}

.hero-logo:hover {
  transform: rotate(-8deg);
}

.hero-title {
  margin: 0.5rem 0 0;
  font-size: clamp(var(--type-2xl), 5vw, var(--display-1));
  font-weight: 800;
  color: var(--text-bright);
  letter-spacing: var(--tracking-tight);
}

.hero-tagline {
  margin: 0.375rem 0 0;
  font-size: var(--type-md);
  color: var(--text-muted);
  max-width: 32rem;
}

.hero-cta {
  margin-top: 1.25rem;
}

/* Cascading hero reveal — each element unfolds with deliberate pacing */
.hero-content > .fade-up:nth-child(1) { animation-delay: 0s; }
.hero-content > .fade-up:nth-child(2) { animation-delay: 0.1s; }
.hero-content > .fade-up:nth-child(3) { animation-delay: 0.2s; }
.hero-content > .fade-up:nth-child(4) { animation-delay: 0.35s; }

/* Product preview in hero — fanned spread of album pages */
.hero-showcase {
  margin-top: 1.25rem;
  padding: 0 0.5rem;
  animation-delay: 0.5s;
}

.hero-fan {
  position: relative;
  width: 100%;
  max-width: 32rem;
  height: 20rem;
  margin: 0 auto;
}

.hero-card {
  position: absolute;
  top: 50%;
  left: 50%;
  border-radius: var(--radius-md);
  overflow: hidden;
  box-shadow: var(--shadow-md);
  --spread: 0rem;
  --s: 1;
  transform: translate(-50%, -50%) translateX(calc(var(--x, 0rem) + var(--spread))) rotate(var(--r, 0deg)) scale(var(--s));
  transition:
    transform var(--duration-normal) ease,
    box-shadow var(--duration-normal) ease,
    opacity var(--duration-normal) ease;
  animation: fan-in 0.6s cubic-bezier(0.34, 1.56, 0.64, 1) backwards;
}

.hero-card:hover,
.hero-card:focus-visible {
  transform: translate(-50%, -50%) translateX(calc(var(--x, 0rem) + var(--spread))) rotate(0deg) scale(1.15);
  z-index: 10 !important;
  box-shadow: var(--shadow-lg);
}

.hero-card:focus-visible {
  outline: 2px solid var(--q-primary);
  outline-offset: 2px;
}

/* Siblings shrink and spread so the hovered/focused card is fully isolated */
.hero-card:has(~ .hero-card:hover),
.hero-card:has(~ .hero-card:focus-visible) {
  --spread: -7rem;
  --s: 0.8;
}

.hero-card:hover ~ .hero-card,
.hero-card:focus-visible ~ .hero-card {
  --spread: 7rem;
  --s: 0.8;
}

.hero-card-img {
  display: block;
  width: 100%;
  aspect-ratio: var(--page-aspect);
}

@keyframes fan-in {
  from {
    opacity: 0;
    transform: translate(-50%, -50%) translateX(0rem) rotate(0deg) scale(0.9);
  }
}

/* Mobile: 3 cards (hide outer two) */
.hero-card:nth-child(1) { --x: -8rem; --r: -6deg; z-index: 1; width: 11rem; display: none; animation-delay: 0.9s; }
.hero-card:nth-child(2) { --x: -5.5rem; --r: -3deg; z-index: 3; width: 12rem; animation-delay: 0.8s; }
.hero-card:nth-child(3) { z-index: 5; width: 14rem; animation-delay: 0.7s; }
.hero-card:nth-child(4) { --x: 5.5rem; --r: 3deg; z-index: 3; width: 12rem; animation-delay: 0.8s; }
.hero-card:nth-child(5) { --x: 8rem; --r: 6deg; z-index: 1; width: 11rem; display: none; animation-delay: 0.9s; }

/* Scroll hint — gentle nudge that content continues */
.hero-scroll-hint {
  margin-top: 0.25rem;
  color: var(--text-faint);
  animation-delay: 1.2s;
  display: flex;
  justify-content: center;
}

.hero-scroll-hint svg {
  animation: scroll-bob 2s ease-in-out infinite;
  animation-delay: 2s;
}

@keyframes scroll-bob {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(4px); }
}

/* Feature bands — varied vertical rhythm creates narrative arc */
.band {
  padding: 2.5rem 1.25rem;
}

.band--default {
  background: var(--bg);
}

.band--accent {
  background: var(--bg-secondary);
}

/* Showstopper band (hike map) — extra vertical breathing room + stronger bg */
.band--showstopper {
  background: var(--bg-deep);
  padding: 3.5rem 1.25rem;
}

/* Standard 50/50 feature (autoAlbum) */
.feature--standard {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1.5rem;
  max-width: 52rem;
  margin: 0 auto;
  width: 100%;
  align-items: center;
}

/* Hero breakout feature (hikeMap) — text above, wide image below */
.feature--hero {
  max-width: 56rem;
  margin: 0 auto;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  align-items: center;
}

.feature--hero .feature-text {
  max-width: 36rem;
}

.feature-picture--wide {
  width: fit-content;
  max-width: 100%;
  margin-inline: auto;
}

.feature-picture--wide .feature-img {
  width: auto;
  max-width: 100%;
  height: auto;
  max-height: clamp(14rem, 45vh, 28rem);
}

/* Paired features (stepPage + overview) — compact supporting detail */
.feature-pair {
  display: grid;
  grid-template-columns: 1fr;
  gap: 2rem;
  max-width: 52rem;
  margin: 0 auto;
  width: 100%;
}

.feature-pair-item {
  display: flex;
  flex-direction: column;
}

.feature-pair-item .feature-picture {
  margin-bottom: 0.75rem;
}

.feature-pair-item .feature-title {
  margin: 0;
}

.feature-pair-item .feature-body {
  margin: 0.375rem 0 0;
}

/* Compact feature (localization) — narrower, centered */
.feature--compact {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1.5rem;
  max-width: 46rem;
  margin: 0 auto;
  width: 100%;
  align-items: center;
}

/* Shared feature atoms */
.feature-picture {
  display: block;
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-md);
  transition:
    transform var(--duration-normal) ease,
    box-shadow var(--duration-normal) ease;
}

.feature-picture:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-lg);
}

.feature-img {
  display: block;
  width: 100%;
  aspect-ratio: var(--page-aspect);
}

.feature-title {
  margin: 0;
  font-size: var(--type-xl);
  font-weight: 700;
  color: var(--text-bright);
  letter-spacing: var(--tracking-tight);
}

.feature-title--lg {
  font-size: clamp(var(--type-2xl), 4vw, var(--display-2));
}

.feature-body {
  margin: 0.75rem 0 0;
  font-size: var(--type-md);
  color: var(--text-muted);
  line-height: 1.65;
}

/* Bottom CTA */
.cta {
  background:
    radial-gradient(ellipse at center 60%, color-mix(in srgb, var(--q-primary) 6%, transparent) 0%, transparent 70%),
    var(--bg-deep);
  padding: 3rem 1.5rem;
  text-align: center;
}

.cta-title {
  margin: 0;
  font-size: clamp(var(--type-2xl), 4vw, var(--display-2));
  font-weight: 700;
  color: var(--text-bright);
  letter-spacing: var(--tracking-tight);
}

.cta-subtitle {
  margin: 1rem 0 0;
  font-size: var(--type-md);
  color: var(--text-muted);
  max-width: 28rem;
  line-height: 1.65;
}

.cta-button {
  margin-top: 2.5rem;
}

/* Tablet — hero scales up, features stay single-column */
@media (min-width: 768px) {
  .hero-content {
    padding: 3rem 2rem 0;
  }

  .hero-logo {
    width: 4rem;
    height: 4rem;
  }

  .hero-title {
    margin: 0.75rem 0 0;
  }

  .hero-tagline {
    font-size: var(--type-xl);
  }

  .hero-showcase {
    margin-top: 2rem;
    padding: 0 2rem;
  }

  /* Tablet fan: all 5 cards visible, proportionally scaled */
  .hero-fan {
    max-width: 44rem;
    height: 22rem;
  }

  .hero-card:nth-child(1) { display: block; --x: -14rem; --r: -8deg; width: 10rem; }
  .hero-card:nth-child(2) { --x: -7.5rem; --r: -4deg; width: 12.5rem; }
  .hero-card:nth-child(3) { width: 15rem; }
  .hero-card:nth-child(4) { --x: 7.5rem; --r: 4deg; width: 12.5rem; }
  .hero-card:nth-child(5) { display: block; --x: 14rem; --r: 8deg; width: 10rem; }

  .band {
    padding: 3.5rem 1.5rem;
  }

  .band--showstopper {
    padding: 4.5rem 1.5rem;
  }

  .feature--hero {
    max-width: 56rem;
    gap: 2rem;
  }

  .feature-title {
    font-size: var(--type-2xl);
  }

  .cta {
    padding: 4.5rem 1.5rem;
  }
}

/* Desktop — multi-column features, full-size hero fan */
@media (min-width: 1024px) {
  .hero-showcase {
    padding: 0 3rem;
  }

  .hero-fan {
    max-width: 60rem;
    height: 26rem;
  }

  .hero-card:nth-child(1) { --x: -20rem; width: 13rem; }
  .hero-card:nth-child(2) { --x: -10.5rem; width: 16rem; }
  .hero-card:nth-child(3) { width: 20rem; }
  .hero-card:nth-child(4) { --x: 10.5rem; width: 16rem; }
  .hero-card:nth-child(5) { --x: 20rem; width: 13rem; }

  .hero-card:has(~ .hero-card:hover),
  .hero-card:has(~ .hero-card:focus-visible) { --spread: -9rem; }
  .hero-card:hover ~ .hero-card,
  .hero-card:focus-visible ~ .hero-card { --spread: 9rem; }

  .band {
    padding: 4.5rem 2rem;
  }

  .band--showstopper {
    padding: 6rem 2rem;
  }

  .feature--standard {
    grid-template-columns: 1fr 1fr;
    gap: 2.5rem;
  }

  .feature-pair {
    grid-template-columns: 1fr 1fr;
    gap: 3rem;
  }

  .feature--compact {
    grid-template-columns: 3fr 2fr;
    gap: 2rem;
  }

  .feature--compact .feature-text {
    order: -1;
  }

  .cta {
    padding: 6rem 2rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .hero-logo,
  .feature-picture,
  .hero-card {
    transition: none;
    animation: none;
  }

  .hero-logo:hover {
    transform: none;
  }

  .feature-picture:hover {
    transform: none;
  }

  .hero-scroll-hint svg {
    animation: none;
  }
}
</style>
