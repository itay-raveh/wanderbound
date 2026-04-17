<script lang="ts" setup>
import { computed, watch } from "vue";
import type { TripMeta } from "@/client";
import { PHASE_ORDER } from "@/composables/useProcessingStream";
import type { PhaseDone, StreamState } from "@/composables/useProcessingStream";
import { useI18n } from "vue-i18n";
import TripTimeline from "./TripTimeline.vue";
import {
  symOutlinedLuggage,
  symOutlinedPinDrop,
  symOutlinedPublic,
} from "@quasar/extras/material-symbols-outlined";
import {
  matCheckCircle,
  matErrorOutline,
  matRefresh,
  matArrowForward,
  matUploadFile,
} from "@quasar/extras/material-icons";

const props = defineProps<{
  trips: TripMeta[];
  state: StreamState;
  tripIndex: number;
  phaseDone: PhaseDone;
  errorDetail: string | null;
}>();

defineEmits<{
  retry: [];
  reupload: [];
  done: [];
}>();

const { t } = useI18n();

const totalSteps = computed(() =>
  props.trips.reduce((sum, trip) => sum + trip.step_count, 0),
);

const totalCountries = computed(() => {
  const codes = new Set(props.trips.flatMap((trip) => trip.country_codes));
  return codes.size;
});

const statusMessage = computed(() => {
  for (const p of PHASE_ORDER) {
    const { done, total } = props.phaseDone[p];
    if (total > 0 && done < total) return t(`phase.status.${p}`);
  }
  return t("register.statusBuilding");
});

watch(
  () => props.state,
  async (s) => {
    if (s !== "done") return;
    const { default: confetti } = await import("canvas-confetti");
    const primary = getComputedStyle(document.documentElement)
      .getPropertyValue("--q-primary")
      .trim();
    void confetti({
      particleCount: 80,
      spread: 70,
      origin: { y: 0.7 },
      colors: [primary, "#fbbf24", "#a78bfa"],
      disableForReducedMotion: true,
    });
  },
);
</script>

<template>
  <q-card class="fade-up">
    <!-- Status + stats -->
    <div class="column no-wrap q-gutter-y-sm" aria-live="polite">
      <span
        v-if="state === 'done'"
        class="status-done row inline no-wrap items-center q-gutter-x-xs text-subtitle2 text-positive"
      >
        <q-icon :name="matCheckCircle" size="1rem" class="done-check" />
        {{ t("register.statusReady") }}
      </span>
      <span v-else-if="state === 'error'" class="text-subtitle2 text-danger">
        {{ t("register.statusError") }}
      </span>
      <span v-else class="status-building text-subtitle2 text-muted">
        <q-spinner-dots size="0.875rem" class="q-mr-xs" />
        <Transition name="fade" mode="out-in">
          <span :key="statusMessage">{{ statusMessage }}</span>
        </Transition>
      </span>

      <div class="stats row items-center wrap q-gutter-x-xs">
        <span
          class="stat row inline no-wrap items-center q-gutter-x-sm text-overline text-faint"
        >
          <q-icon :name="symOutlinedLuggage" size="0.875rem" />
          <template v-if="state === 'running' && trips.length > 1">
            {{
              t("register.tripsProgress", {
                current: tripIndex + 1,
                total: trips.length,
              })
            }}
          </template>
          <template v-else>
            {{ t("register.trips", trips.length) }}
          </template>
        </span>
        <span class="text-faint" aria-hidden="true">&middot;</span>
        <span
          class="stat row inline no-wrap items-center q-gutter-x-sm text-overline text-faint"
        >
          <q-icon :name="symOutlinedPinDrop" size="0.875rem" />
          {{ t("register.steps", totalSteps) }}
        </span>
        <span class="text-faint" aria-hidden="true">&middot;</span>
        <span
          class="stat row inline no-wrap items-center q-gutter-x-sm text-overline text-faint"
        >
          <q-icon :name="symOutlinedPublic" size="0.875rem" />
          {{ t("register.countries", totalCountries) }}
        </span>
      </div>
    </div>

    <q-separator class="q-my-md" />

    <!-- Trip timeline -->
    <TripTimeline
      :trips="trips"
      :state="state"
      :trip-index="tripIndex"
      :phase-done="phaseDone"
    />

    <!-- Error state -->
    <div v-if="state === 'error'" class="fade-up">
      <q-separator class="q-my-lg" />
      <div class="error-banner row no-wrap q-gutter-x-sm">
        <q-icon
          :name="matErrorOutline"
          size="1.25rem"
          class="error-icon text-danger"
        />
        <div class="error-body column no-wrap q-gutter-y-sm">
          <span class="text-body2 error-msg text-muted">{{ errorDetail }}</span>
          <div class="row q-gutter-sm">
            <q-btn
              outline
              no-caps
              dense
              :icon="matRefresh"
              :label="t('register.tryAgain')"
              class="retry-btn bg-surface"
              @click="$emit('retry')"
            />
            <q-btn
              outline
              no-caps
              dense
              :icon="matUploadFile"
              :label="t('register.uploadAgain')"
              class="retry-btn bg-surface"
              @click="$emit('reupload')"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- Done state -->
    <div v-if="state === 'done'" class="fade-up">
      <q-separator class="q-my-lg" />
      <q-btn
        color="primary"
        unelevated
        no-caps
        class="done-btn full-width text-subtitle1"
        @click="$emit('done')"
      >
        {{ t("register.openAlbum") }}
        <q-icon :name="matArrowForward" size="1rem" class="rtl-flip" />
      </q-btn>
    </div>
  </q-card>
</template>

<style scoped>
.status-building {
  display: inline-flex;
  align-items: center;
}

.error-banner {
  padding: var(--gap-lg);
  border-radius: var(--radius-md);
  border: 1px solid var(--danger);
  background: color-mix(in srgb, var(--danger) 6%, var(--bg-secondary));
}

.error-icon {
  flex-shrink: 0;
  margin-top: 1px; /* optical alignment with text baseline */
}

.error-msg {
  line-height: 1.5;
}

.retry-btn {
  border-color: var(--border-color);
  color: var(--text);
  align-self: flex-start;
  transition:
    border-color var(--duration-fast) ease,
    background var(--duration-fast) ease;
}

.retry-btn:hover {
  border-color: var(--text-faint);
  background: var(--surface);
}

.done-check {
  animation: scaleIn var(--duration-normal) cubic-bezier(0.25, 1, 0.5, 1) both;
}

@keyframes scaleIn {
  from {
    transform: scale(0);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}

.done-btn {
  animation: ctaGlow 0.8s ease-out 0.4s both;
  transition:
    transform var(--duration-fast) cubic-bezier(0.25, 1, 0.5, 1),
    box-shadow var(--duration-fast) ease;
}

@keyframes ctaGlow {
  0% {
    box-shadow: 0 0 0 0 color-mix(in srgb, var(--q-primary) 35%, transparent);
  }
  100% {
    box-shadow: 0 0 0 0.5rem
      color-mix(in srgb, var(--q-primary) 0%, transparent);
  }
}

.done-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 0.25rem 0.75rem
    color-mix(in srgb, var(--q-primary) 30%, transparent);
}

.done-btn:active {
  transform: translateY(0);
  box-shadow: none;
}

@media (prefers-reduced-motion: reduce) {
  .done-check,
  .done-btn,
  .retry-btn {
    animation: none;
    transition: none;
  }
}
</style>
