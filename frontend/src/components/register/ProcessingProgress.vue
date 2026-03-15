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
  <div class="processing-card">
    <!-- Header -->
    <div class="header">
      <div class="greeting">
        <span class="text-h6 greeting-hey">Hey {{ user.first_name }},</span>
        <span v-if="state === 'done'" class="text-subtitle2 greeting-sub done-sub">
          your album is ready
        </span>
        <span v-else-if="state === 'error'" class="text-subtitle2 greeting-sub error-sub">
          something went wrong
        </span>
        <span v-else class="text-subtitle2 greeting-sub"> building your album </span>
      </div>

      <div class="stats">
        <span class="stat text-overline">
          <q-icon :name="symOutlinedLuggage" size="var(--text-md)" />
          {{ trips.length }} trip{{ trips.length !== 1 ? "s" : "" }}
        </span>
        <span class="stat-dot" />
        <span class="stat text-overline">
          <q-icon :name="symOutlinedPinDrop" size="var(--text-md)" />
          {{ totalSteps }} steps
        </span>
        <span class="stat-dot" />
        <span class="stat text-overline">
          <q-icon :name="symOutlinedPublic" size="var(--text-md)" />
          {{ totalCountries }} countr{{ totalCountries !== 1 ? "ies" : "y" }}
        </span>
      </div>
    </div>

    <div class="divider" />

    <!-- Trip timeline -->
    <TripTimeline
      :trips="trips"
      :state="state"
      :trip-index="tripIndex"
      :phase-done="phaseDone"
    />

    <!-- Error state -->
    <template v-if="state === 'error'">
      <div class="divider" />
      <div class="error-banner">
        <q-icon :name="matErrorOutline" size="1.25rem" class="error-icon" />
        <div class="error-body">
          <span class="text-body2 error-msg">{{ errorDetail }}</span>
          <button class="retry-btn text-body2" @click="$emit('retry')">
            <q-icon :name="matRefresh" size="var(--text-md)" />
            Try again
          </button>
        </div>
      </div>
    </template>

    <!-- Done state -->
    <template v-if="state === 'done'">
      <div class="divider" />
      <button class="done-btn text-subtitle1" @click="$emit('done')">
        Open your album
        <q-icon :name="matArrowForward" size="1rem" />
      </button>
    </template>
  </div>
</template>

<style scoped>
.processing-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: 1.75rem 2rem;
  animation: fadeUp 0.5s ease both;
}

.header {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.greeting {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.greeting-hey {
  color: var(--text-bright);
}

.greeting-sub {
  color: var(--text-muted);
}

.done-sub {
  color: var(--q-positive);
}

.error-sub {
  color: var(--danger);
}

.stats {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.stat {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  color: var(--text-faint);
}

.stat-dot {
  width: 0.1875rem;
  height: 0.1875rem;
  border-radius: 50%;
  background: var(--border-color);
  flex-shrink: 0;
}

.divider {
  height: 1px;
  background: var(--border-color);
  margin: 1.25rem 0;
}

.error-banner {
  display: flex;
  gap: 0.625rem;
  padding: 1rem;
  border-radius: var(--radius-md);
  border: 1px solid var(--danger);
  background: color-mix(in srgb, var(--danger) 6%, var(--bg-secondary));
}

.error-icon {
  color: var(--danger);
  flex-shrink: 0;
  margin-top: 0.0625rem;
}

.error-body {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.error-msg {
  color: var(--text-muted);
  line-height: 1.5;
}

.retry-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.75rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--surface);
  color: var(--text);
  font-weight: 500;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    background 0.2s ease;
  width: fit-content;
}

.retry-btn:hover {
  border-color: var(--text-faint);
  background: var(--bg-secondary);
}

.done-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.75rem 1rem;
  border-radius: var(--radius-md);
  border: none;
  background: var(--q-primary);
  color: #fff;
  cursor: pointer;
  transition:
    background 0.2s ease,
    transform 0.1s ease;
  animation: fadeUp 0.5s ease both;
}

.done-btn:hover {
  background: color-mix(in srgb, var(--q-primary) 85%, #000);
}

.done-btn:active {
  transform: scale(0.98);
}
</style>
