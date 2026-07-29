<script lang="ts" setup>
import { authenticate, createDemo } from "@/client";
import AuthActions from "@/components/landing/AuthActions.vue";
import LandingImage from "@/components/landing/LandingImage.vue";
import { microsoftLogin } from "@/composables/useMicrosoftAuth";
import { isLocalLoginEnabled } from "@/config";
import { useAuthStateQuery } from "@/queries/useAuthStateQuery";
import type { Provider } from "@/router";
import {
  usePreferredReducedMotion,
  useIntersectionObserver,
} from "@vueuse/core";
import { useQueryCache } from "@pinia/colada";
import { useQuasar } from "quasar";
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { queryKeys } from "@/queries/keys";

const { t } = useI18n();
const router = useRouter();
const $q = useQuasar();
const cache = useQueryCache();
const localLoginEnabled = isLocalLoginEnabled();

const { data: authStateData } = useAuthStateQuery();
const authenticated = computed(
  () => authStateData.value?.state === "authenticated",
);

const mode = computed(() => ($q.dark.isActive ? "dark" : "light"));

async function handleLogin(credential: string, provider: Provider) {
  const { data: user } = await authenticate({
    body: { credential },
    path: { provider },
  });
  void cache.invalidateQueries({ key: queryKeys.authState() });
  if (user) {
    await router.push({ name: "editor" });
  } else {
    await router.push({ name: "upload" });
  }
}

function notifyLoginFailed() {
  $q.notify({ type: "negative", message: t("login.signInFailed") });
}

function onGoogleLogin(credential: string) {
  void handleLogin(credential, "google").catch(notifyLoginFailed);
}

async function onMicrosoftLogin() {
  try {
    const idToken = await microsoftLogin();
    await handleLogin(idToken, "microsoft");
  } catch {
    notifyLoginFailed();
  }
}

const demoLoading = ref(false);

async function onTryDemo() {
  demoLoading.value = true;
  try {
    const { data } = await createDemo({ throwOnError: true });
    void cache.invalidateQueries({ key: queryKeys.authState() });
    await router.push({ name: "upload", state: { uploadResult: data } });
  } catch {
    $q.notify({ type: "negative", message: t("login.signInFailed") });
  } finally {
    demoLoading.value = false;
  }
}

const mainRef = ref<HTMLElement>();

/* 3D tilt on hero card fan - tracks cursor across the entire hero section */
const heroRef = ref<HTMLElement>();
const reducedMotion = usePreferredReducedMotion();
let tiltFrame = 0;

function onHeroMouseMove(e: MouseEvent) {
  const el = heroRef.value;
  if (!el || reducedMotion.value === "reduce") return;
  if ((e.target as HTMLElement).closest(".hero-card")) return;
  const { clientX, clientY } = e;
  cancelAnimationFrame(tiltFrame);
  tiltFrame = requestAnimationFrame(() => {
    const rect = el.getBoundingClientRect();
    const x = (clientX - rect.left) / rect.width - 0.5;
    const y = (clientY - rect.top) / rect.height - 0.5;
    el.style.setProperty("--tilt-x", `${(y * -10).toFixed(2)}deg`);
    el.style.setProperty("--tilt-y", `${(x * 16).toFixed(2)}deg`);
  });
}

function onHeroMouseLeave() {
  cancelAnimationFrame(tiltFrame);
  heroRef.value?.style.removeProperty("--tilt-x");
  heroRef.value?.style.removeProperty("--tilt-y");
}

/* Scroll-driven feature reveals via IntersectionObserver */
const revealTargets = ref<HTMLElement[]>([]);
const { stop: stopReveal } = useIntersectionObserver(
  revealTargets,
  (entries, observer) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        (entry.target as HTMLElement).classList.add("revealed");
        observer.unobserve(entry.target);
      }
    }
  },
  { threshold: 0.12 },
);

onMounted(() => {
  if (reducedMotion.value === "reduce") {
    stopReveal();
    return;
  }
  revealTargets.value = Array.from(
    mainRef.value?.querySelectorAll<HTMLElement>(".scroll-reveal") ?? [],
  );
});

onUnmounted(() => cancelAnimationFrame(tiltFrame));
</script>

<template>
  <main ref="mainRef">
    <!-- Hero -->
    <section
      ref="heroRef"
      class="hero"
      aria-labelledby="hero-heading"
      @mousemove="onHeroMouseMove"
      @mouseleave="onHeroMouseLeave"
    >
      <div class="hero-content column no-wrap items-center">
        <div class="hero-brand fade-up">
          <img src="/logo.svg" alt="" class="hero-logo" />
          <h1 id="hero-heading" class="hero-title">{{ t("brand") }}</h1>
        </div>
        <i18n-t keypath="tagline" tag="p" class="hero-tagline fade-up">
          <template #polarsteps
            ><span class="polarsteps">Polarsteps</span></template
          >
        </i18n-t>
      </div>

      <!-- Hero showcase: fanned spread of different album page types -->
      <div class="hero-showcase fade-up">
        <div class="hero-fan" aria-hidden="true">
          <LandingImage name="cover" :mode="mode" class="hero-card" />
          <LandingImage name="hike-map" :mode="mode" class="hero-card" />
          <LandingImage
            name="step-page"
            :mode="mode"
            class="hero-card"
            fetchpriority="high"
          />
          <LandingImage name="overview" :mode="mode" class="hero-card" />
          <LandingImage name="auto-album" :mode="mode" class="hero-card" />
        </div>
      </div>

      <div class="hero-cta fade-up">
        <AuthActions
          :authenticated="authenticated"
          :demo-loading="demoLoading"
          :local-login-enabled="localLoginEnabled"
          @google="onGoogleLogin"
          @microsoft="onMicrosoftLogin"
          @demo="onTryDemo"
        />
      </div>
    </section>

    <!-- Feature: autoAlbum - core product showcase, standard 50/50 -->
    <section class="band band--default" aria-labelledby="auto-album-heading">
      <div class="feature feature--standard scroll-reveal">
        <LandingImage
          name="auto-album"
          :mode="mode"
          sizes="(min-width: 1024px) 480px, 100vw"
          :alt="t('landing.autoAlbumTitle')"
          loading="lazy"
          class="feature-picture"
        />
        <div class="feature-text">
          <h2 id="auto-album-heading" class="feature-title">
            {{ t("landing.autoAlbumTitle") }}
          </h2>
          <i18n-t keypath="landing.autoAlbumBody" tag="p" class="feature-body">
            <template #polarsteps
              ><span class="polarsteps">Polarsteps</span></template
            >
          </i18n-t>
        </div>
      </div>
    </section>

    <!-- Feature: hikeMap - visually stunning, full-width breakout -->
    <section class="band band--showstopper" aria-labelledby="hike-map-heading">
      <div class="feature feature--hero scroll-reveal">
        <div class="feature-text">
          <h2 id="hike-map-heading" class="feature-title feature-title--lg">
            {{ t("landing.hikeMapTitle") }}
          </h2>
          <p class="feature-body">{{ t("landing.hikeMapBody") }}</p>
        </div>
        <LandingImage
          name="hike-map"
          :mode="mode"
          sizes="(min-width: 1024px) 960px, 100vw"
          :alt="t('landing.hikeMapTitle')"
          loading="lazy"
          class="feature-picture feature-picture--wide"
        />
      </div>
    </section>

    <!-- Features: localization + overview - paired features -->
    <div class="band band--default">
      <div class="feature-pair">
        <section
          class="feature-pair-item scroll-reveal"
          aria-labelledby="localization-heading"
        >
          <LandingImage
            name="localization"
            :mode="mode"
            sizes="(min-width: 1024px) 480px, 100vw"
            :alt="t('landing.localizationTitle')"
            loading="lazy"
            class="feature-picture"
          />
          <h2 id="localization-heading" class="feature-title">
            {{ t("landing.localizationTitle") }}
          </h2>
          <i18n-t
            keypath="landing.localizationBody"
            tag="p"
            class="feature-body"
          >
            <template #polarsteps
              ><span class="polarsteps">Polarsteps</span></template
            >
          </i18n-t>
        </section>
        <section
          class="feature-pair-item scroll-reveal"
          aria-labelledby="overview-heading"
        >
          <LandingImage
            name="overview"
            :mode="mode"
            sizes="(min-width: 1024px) 480px, 100vw"
            :alt="t('landing.overviewTitle')"
            loading="lazy"
            class="feature-picture"
          />
          <h2 id="overview-heading" class="feature-title">
            {{ t("landing.overviewTitle") }}
          </h2>
          <p class="feature-body">{{ t("landing.overviewBody") }}</p>
        </section>
      </div>
    </div>

  </main>
</template>

<style scoped src="./LandingView.css"></style>
