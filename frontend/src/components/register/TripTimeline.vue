<script lang="ts" setup>
import { computed } from "vue";
import type { ProcessingPhase, TripMeta } from "@/client";
import { PHASE_ORDER } from "@/composables/useProcessingStream";
import type { PhaseDone, StreamState } from "@/composables/useProcessingStream";
import { useI18n } from "vue-i18n";
import { matCheck, matCheckCircle, matTerrain, matThermostat, matPhotoLibrary } from "@quasar/extras/material-icons";

const props = defineProps<{
  trips: TripMeta[];
  state: StreamState;
  tripIndex: number;
  phaseDone: PhaseDone;
}>();

const { t } = useI18n();

const PHASE_ICONS: Record<ProcessingPhase, string> = {
  elevations: matTerrain,
  weather: matThermostat,
  layouts: matPhotoLibrary,
};

type ItemStatus = "pending" | "active" | "done";

function tripStatus(index: number): ItemStatus {
  if (props.state === "done") return "done";
  if (index < props.tripIndex) return "done";
  if (index === props.tripIndex) return "active";
  return "pending";
}

const tripStatuses = computed(() =>
  props.trips.map((_, i) => tripStatus(i)),
);

function phaseStatus(phase: ProcessingPhase): ItemStatus {
  const { done, total } = props.phaseDone[phase];
  if (done >= total && total > 0) return "done";
  if (total > 0) return "active";
  return "pending";
}

const phaseStatuses = computed(() =>
  Object.fromEntries(PHASE_ORDER.map((p) => [p, phaseStatus(p)])) as Record<ProcessingPhase, ItemStatus>,
);

function phasePercent(phase: ProcessingPhase): number {
  const { done, total } = props.phaseDone[phase];
  if (!total) return 0;
  return Math.round((done / total) * 100);
}

const anyPhaseStarted = computed(() =>
  PHASE_ORDER.some((p) => props.phaseDone[p].total > 0),
);

const overallPercent = computed(() => {
  let totalSum = 0;
  let doneSum = 0;
  for (const p of PHASE_ORDER) {
    const { done, total } = props.phaseDone[p];
    if (total > 0) {
      totalSum += total;
      doneSum += done;
    }
  }
  if (!totalSum) return 0;
  return Math.round((doneSum / totalSum) * 100);
});
</script>

<template>
  <div class="trips column no-wrap">
    <div
      v-for="(trip, i) in trips"
      :key="trip.id"
      class="trip row no-wrap"
      :class="tripStatuses[i]"
    >
      <!-- Timeline connector -->
      <div class="trip-rail column no-wrap items-center">
        <div class="trip-dot relative-position flex flex-center">
          <q-icon
            v-if="tripStatuses[i] === 'done'"
            :name="matCheck"
            size="0.75rem"
          />
          <div
            v-else-if="tripStatuses[i] === 'active'"
            class="trip-dot-pulse"
          />
        </div>
        <div v-if="i < trips.length - 1" class="trip-line" />
      </div>

      <!-- Trip content -->
      <div class="trip-content">
        <div class="row no-wrap items-baseline justify-between q-gutter-x-sm">
          <span class="trip-title text-subtitle1 ellipsis text-bright" :title="trip.title">{{ trip.title }}</span>
          <span class="trip-meta text-overline text-faint">
            {{ t("register.steps", trip.step_count) }}
          </span>
        </div>

        <!-- Phase progress (only for active trip) -->
        <div v-if="tripStatuses[i] === 'active' && anyPhaseStarted" class="column no-wrap q-mt-sm q-gutter-y-xs">
          <div
            v-for="p in PHASE_ORDER"
            :key="p"
            class="phase row no-wrap items-center text-caption"
            :class="phaseStatuses[p]"
          >
            <q-icon
              :name="PHASE_ICONS[p]"
              size="0.75rem"
              class="phase-icon"
            />
            <span class="phase-label text-no-wrap">{{ t(`phase.${p}`) }}</span>

            <q-icon
              v-if="phaseStatuses[p] === 'done'"
              :name="matCheckCircle"
              size="0.75rem"
              class="phase-check text-primary"
            />
            <span v-else-if="phaseStatuses[p] === 'active' && phaseDone[p].total > 0" class="phase-count text-overline text-faint">
              {{ phaseDone[p].done }}/{{ phaseDone[p].total }}
            </span>

            <!-- Per-phase mini progress bar (only for multi-item phases) -->
            <div v-if="phaseStatuses[p] === 'active' && phaseDone[p].total > 0" class="phase-track overflow-hidden" aria-hidden="true">
              <div
                class="phase-fill"
                :style="{ width: `${phasePercent(p)}%` }"
              />
            </div>
          </div>

          <!-- Overall progress bar -->
          <div class="progress-track overflow-hidden" role="progressbar" :aria-valuenow="overallPercent" aria-valuemin="0" aria-valuemax="100">
            <div
              class="progress-fill relative-position"
              :style="{ width: `${overallPercent}%` }"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.trip {
  gap: var(--gap-md-lg);
  transition: opacity var(--duration-fast) ease;
}

.trip.pending {
  opacity: 0.4;
}

.trip.active,
.trip.done {
  opacity: 1;
}

.trip-rail {
  padding-top: var(--gap-xs);
  width: 1.25rem;
  flex-shrink: 0;
}

.trip-dot {
  width: 1.25rem;
  height: 1.25rem;
  border-radius: 50%;
  border: 2px solid var(--border-color);
  flex-shrink: 0;
  background: var(--bg-secondary);
  transition:
    border-color var(--duration-normal) ease,
    background var(--duration-normal) ease;
  z-index: 1;
}

.trip.done .trip-dot {
  border-color: var(--q-primary);
  background: var(--q-primary);
  color: white;
}

.trip.active .trip-dot {
  border-color: var(--q-primary);
}

.trip-dot-pulse {
  width: 0.375rem;
  height: 0.375rem;
  border-radius: 50%;
  background: var(--q-primary);
  animation: pulse 1.8s ease-in-out infinite;
}

.trip-line {
  width: 2px;
  flex: 1;
  min-height: 1rem;
  background: var(--border-color);
  position: relative;
  overflow: hidden;
}

.trip-line::after {
  content: "";
  position: absolute;
  inset: 0;
  background: var(--q-primary);
  transform: scaleY(0);
  transform-origin: top;
  transition: transform var(--duration-slow) cubic-bezier(0.25, 1, 0.5, 1);
}

.trip.done .trip-line::after {
  transform: scaleY(1);
}

.trip-content {
  flex: 1;
  min-width: 0;
  padding-bottom: 1.25rem;
}

.trip:last-child .trip-content {
  padding-bottom: 0;
}

.trip-meta {
  text-transform: none;
  flex-shrink: 0;
}

.phase {
  gap: var(--gap-sm-md);
  color: var(--text-faint);
  transition: color var(--duration-normal) ease;
  height: 1.375rem;
}

.phase.done {
  color: var(--text-muted);
}

.phase.active {
  color: var(--q-primary);
  font-weight: 600;
}

.phase-icon {
  flex-shrink: 0;
}

.phase.active .phase-icon {
  animation: pulse 1.8s ease-in-out infinite;
}

.phase-count {
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.phase-check {
  opacity: 0.6;
  animation: scaleIn var(--duration-normal) cubic-bezier(0.25, 1, 0.5, 1) both;
}

@keyframes scaleIn {
  from {
    transform: scale(0);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 0.6;
  }
}

.phase-track {
  flex: 1;
  height: 0.1875rem;
  border-radius: var(--radius-xs);
  background: color-mix(in srgb, var(--q-primary) 12%, transparent);
  min-width: 2rem;
}

.phase-fill {
  height: 100%;
  border-radius: var(--radius-xs);
  background: var(--q-primary);
  transition: width var(--duration-slow) cubic-bezier(0.4, 0, 0.2, 1);
}

.progress-track {
  height: 0.25rem;
  border-radius: var(--radius-xs);
  background: color-mix(in srgb, var(--q-primary) 12%, transparent);
  margin-top: var(--gap-md);
}

.progress-fill {
  height: 100%;
  border-radius: var(--radius-xs);
  background: var(--q-primary);
  transition: width var(--duration-slow) cubic-bezier(0.4, 0, 0.2, 1);
}

.progress-fill::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    transparent,
    color-mix(in srgb, var(--text-bright) 20%, transparent),
    transparent
  );
  animation: shimmer 2s ease-in-out infinite;
}

@media (prefers-reduced-motion: reduce) {
  .trip-dot-pulse,
  .phase.active .phase-icon,
  .progress-fill::after,
  .phase-check {
    animation: none;
  }

  .trip-line::after {
    transition: none;
  }
}
</style>
