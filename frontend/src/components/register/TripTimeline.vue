<script lang="ts" setup>
import { computed } from "vue";
import type { TripMeta } from "@/client/types.gen";
import type { ProcessingPhase, StreamState } from "@/composables/useProcessingStream";

const props = defineProps<{
  trips: TripMeta[];
  state: StreamState;
  tripIndex: number;
  phase: ProcessingPhase | null;
  phaseDone: number;
}>();

const phaseTotal = computed(() => props.trips[props.tripIndex]?.step_count ?? 0);

const PHASE_ORDER: ProcessingPhase[] = [
  "elevations",
  "weather",
  "layouts",
];

const PHASE_LABELS: Record<ProcessingPhase, string> = {
  elevations: "Mapping terrain",
  weather: "Checking weather",
  layouts: "Arranging photos",
};

const PHASE_ICONS: Record<ProcessingPhase, string> = {
  elevations: "terrain",
  weather: "thermostat",
  layouts: "photo_library",
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

function phaseStatus(tripIdx: number, phase: ProcessingPhase): ItemStatus {
  const trip = tripStatus(tripIdx);
  if (trip === "done") return "done";
  if (trip === "pending") return "pending";
  if (!props.phase) return "pending";
  const currentIdx = PHASE_ORDER.indexOf(props.phase);
  const phaseIdx = PHASE_ORDER.indexOf(phase);
  if (phaseIdx < currentIdx) return "done";
  if (phaseIdx > currentIdx) return "pending";
  return props.phaseDone >= phaseTotal.value ? "done" : "active";
}

const progressPercent = computed(() => {
  if (!phaseTotal.value) return 0;
  return Math.round((props.phaseDone / phaseTotal.value) * 100);
});
</script>

<template>
  <div class="trips">
    <div
      v-for="(trip, i) in trips"
      :key="trip.id"
      class="trip"
      :class="tripStatuses[i]"
    >
      <!-- Timeline connector -->
      <div class="trip-rail">
        <div class="trip-dot">
          <q-icon
            v-if="tripStatuses[i] === 'done'"
            name="check"
            size="var(--text-sm)"
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
        <div class="trip-header">
          <span class="trip-title text-subtitle1">{{ trip.title }}</span>
          <span class="trip-meta text-overline">
            {{ trip.step_count }} step{{ trip.step_count !== 1 ? "s" : "" }}
          </span>
        </div>

        <!-- Phase progress (only for active trip) -->
        <div v-if="tripStatuses[i] === 'active' && phase" class="phases">
          <div
            v-for="p in PHASE_ORDER"
            :key="p"
            class="phase text-caption"
            :class="phaseStatus(i, p)"
          >
            <q-icon
              :name="PHASE_ICONS[p]"
              size="var(--text-sm)"
              class="phase-icon"
            />
            <span class="phase-label">{{ PHASE_LABELS[p] }}</span>
            <q-icon
              v-if="phaseStatus(i, p) === 'done'"
              name="check_circle"
              size="var(--text-sm)"
              class="phase-check"
            />
          </div>

          <!-- Progress bar -->
          <div class="progress-track">
            <div
              class="progress-fill"
              :style="{ width: `${progressPercent}%` }"
            />
          </div>
          <div class="progress-label text-overline">
            {{ phaseDone }} / {{ phaseTotal }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.trips {
  display: flex;
  flex-direction: column;
}

.trip {
  display: flex;
  gap: 0.75rem;
  transition: opacity 0.3s ease;
}

.trip.pending {
  opacity: 0.4;
}

.trip.active,
.trip.done {
  opacity: 1;
}

/* ── Rail ── */

.trip-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 0.125rem;
  width: 1.25rem;
  flex-shrink: 0;
}

.trip-dot {
  width: 1.25rem;
  height: 1.25rem;
  border-radius: 50%;
  border: 2px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: var(--bg-secondary);
  transition:
    border-color 0.3s ease,
    background 0.3s ease;
  position: relative;
  z-index: 1;
}

.trip.done .trip-dot {
  border-color: var(--q-primary);
  background: var(--q-primary);
  color: #fff;
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
  transition: background 0.3s ease;
}

.trip.done .trip-line {
  background: var(--q-primary);
}

/* ── Trip content ── */

.trip-content {
  flex: 1;
  min-width: 0;
  padding-bottom: 1.25rem;
}

.trip:last-child .trip-content {
  padding-bottom: 0;
}

.trip-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
}

.trip-title {
  color: var(--text-bright);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.trip-meta {
  color: var(--text-faint);
  text-transform: none;
  flex-shrink: 0;
}

/* ── Phases ── */

.phases {
  margin-top: 0.625rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.phase {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  color: var(--text-faint);
  transition:
    color 0.3s ease,
    opacity 0.3s ease;
  opacity: 0.5;
  height: 1.375rem;
}

.phase.done {
  color: var(--text-muted);
  opacity: 0.7;
}

.phase.active {
  color: var(--q-primary);
  opacity: 1;
  font-weight: 600;
}

.phase-icon {
  flex-shrink: 0;
}

.phase.active .phase-icon {
  animation: pulse 1.8s ease-in-out infinite;
}

.phase-label {
  flex: 1;
}

.phase-check {
  color: var(--q-primary);
  opacity: 0.6;
}

/* ── Progress bar ── */

.progress-track {
  height: 0.25rem;
  border-radius: 0.125rem;
  background: color-mix(in srgb, var(--q-primary) 12%, transparent);
  margin-top: 0.5rem;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 0.125rem;
  background: var(--q-primary);
  transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
}

.progress-fill::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(255, 255, 255, 0.2),
    transparent
  );
  animation: shimmer 2s ease-in-out infinite;
}

.progress-label {
  color: var(--text-faint);
  text-transform: none;
  margin-top: 0.25rem;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
</style>
