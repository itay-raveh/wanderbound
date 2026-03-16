<script lang="ts" setup>
import { computed } from "vue";
import type { TripMeta, User } from "@/client/types.gen";
import type { PhaseDone, StreamState } from "@/composables/useProcessingStream";
import TripTimeline from "./TripTimeline.vue";
import { symOutlinedLuggage, symOutlinedPinDrop, symOutlinedPublic } from "@quasar/extras/material-symbols-outlined";
import { matErrorOutline, matRefresh, matArrowForward } from "@quasar/extras/material-icons";

const props = defineProps<{
  trips: TripMeta[];
  user: User;
  state: StreamState;
  tripIndex: number;
  phaseDone: PhaseDone;
  errorDetail: string | null;
}>();

defineEmits<{
  retry: [];
  done: [];
}>();

const totalSteps = computed(() =>
  props.trips.reduce((sum, t) => sum + t.step_count, 0),
);

const totalCountries = computed(() => {
  const codes = new Set(props.trips.flatMap((t) => t.country_codes));
  return codes.size;
});
</script>

<template>
  <q-card class="processing-card fade-up">
    <!-- Header -->
    <div class="column no-wrap q-gutter-y-sm">
      <div class="greeting column no-wrap">
        <span class="text-h6 text-bright">Hey {{ user.first_name }},</span>
        <span v-if="state === 'done'" class="text-subtitle2 text-positive">
          your album is ready
        </span>
        <span v-else-if="state === 'error'" class="text-subtitle2 text-danger">
          something went wrong
        </span>
        <span v-else class="text-subtitle2 text-muted"> building your album </span>
      </div>

      <div class="stats row items-center wrap q-gutter-sm">
        <span class="stat row inline no-wrap items-center q-gutter-x-xs text-overline text-faint">
          <q-icon :name="symOutlinedLuggage" size="0.875rem" />
          {{ trips.length }} trip{{ trips.length !== 1 ? "s" : "" }}
        </span>
        <span class="stat-dot" />
        <span class="stat row inline no-wrap items-center q-gutter-x-xs text-overline text-faint">
          <q-icon :name="symOutlinedPinDrop" size="0.875rem" />
          {{ totalSteps }} steps
        </span>
        <span class="stat-dot" />
        <span class="stat row inline no-wrap items-center q-gutter-x-xs text-overline text-faint">
          <q-icon :name="symOutlinedPublic" size="0.875rem" />
          {{ totalCountries }} countr{{ totalCountries !== 1 ? "ies" : "y" }}
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
    <template v-if="state === 'error'">
      <q-separator class="q-my-md" />
      <div class="error-banner row no-wrap q-gutter-x-sm">
        <q-icon :name="matErrorOutline" size="1.25rem" class="error-icon text-danger" />
        <div class="error-body column no-wrap q-gutter-y-sm">
          <span class="text-body2 error-msg text-muted">{{ errorDetail }}</span>
          <q-btn outline no-caps dense :icon="matRefresh" label="Try again" class="retry-btn bg-surface" @click="$emit('retry')" />
        </div>
      </div>
    </template>

    <!-- Done state -->
    <template v-if="state === 'done'">
      <q-separator class="q-my-md" />
      <q-btn
        color="primary"
        unelevated
        no-caps
        class="fade-up full-width text-subtitle1"
        @click="$emit('done')"
      >
        Open your album
        <q-icon :name="matArrowForward" size="1rem" />
      </q-btn>
    </template>
  </q-card>
</template>

<style scoped>
.processing-card {
  padding: 1.75rem 2rem;
}

.greeting {
  gap: var(--gap-xs);
}

.stat-dot {
  width: 0.1875rem;
  height: 0.1875rem;
  border-radius: 50%;
  background: var(--border-color);
  flex-shrink: 0;
}

.error-banner {
  padding: 1rem;
  border-radius: var(--radius-md);
  border: 1px solid var(--danger);
  background: color-mix(in srgb, var(--danger) 6%, var(--bg-secondary));
}

.error-icon {
  flex-shrink: 0;
  margin-top: 0.0625rem;
}

.error-msg {
  line-height: 1.5;
}

.retry-btn {
  border-color: var(--border-color);
  color: var(--text);
}

</style>
