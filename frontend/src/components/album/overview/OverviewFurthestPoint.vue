<script lang="ts" setup>
import { type Location, type Step } from "@/client";
import { useUserQuery } from "@/queries/useUserQuery";
import { flagUrl } from "@/utils/media";
import { chooseTextDir } from "@/utils/text";
import { distance, point } from "@turf/turf";
import { computed } from "vue";

const props = defineProps<{
  home: Location;
  steps: Step[];
}>();

const { formatDistance, distanceUnit, formatDate } = useUserQuery();

const furthest = computed(() => {
  let maxDist = -1;
  let bestStep = props.steps[0]!;
  const homePoint = point([props.home.lon, props.home.lat]);

  for (const step of props.steps) {
    const dist = distance(
      homePoint,
      point([step.location.lon, step.location.lat]),
      { units: "kilometers" },
    );
    if (dist > maxDist) {
      maxDist = dist;
      bestStep = step;
    }
  }

  const dateStr = formatDate(new Date(bestStep.datetime), {
    month: "short",
    day: "numeric",
  });
  return {
    location: bestStep.location,
    dist: formatDistance(maxDist),
    date: dateStr,
    dateDir: chooseTextDir(dateStr),
  };
});
</script>

<template>
  <div class="furthest">
    <div class="fp-top">
      <q-icon name="home" size="1.375rem" class="fp-top-icon" />
      <q-icon name="place" size="1.375rem" class="fp-top-icon" />
    </div>

    <div class="fp-body">
      <!-- Home -->
      <div class="fp-info">
        <div class="fp-name">{{ home.name }}</div>
        <div class="fp-sub">
          <q-img
            :src="flagUrl(home.country_code)"
            class="fp-flag"
            loading="eager"
          />
          <span>{{ home.detail }}</span>
        </div>
      </div>

      <!-- Trail with distance badge -->
      <div class="fp-trail">
        <div class="fp-line" />
        <div class="column">
          <span class="fp-tag">Furthest from home</span>
          <div class="fp-badge">
            <span class="fp-dist">{{ furthest.dist }}</span>
            <span class="fp-unit">{{ distanceUnit() }}</span>
          </div>
        </div>
        <div class="fp-line" />
      </div>

      <!-- Furthest -->
      <div class="fp-info right">
        <div class="fp-name">{{ furthest.location.name }}</div>
        <div class="fp-sub">
          <span :dir="furthest.dateDir">{{ furthest.date }}</span>
          <span class="fp-sep">·</span>
          <span>{{ furthest.location.detail }}</span>
          <q-img
            :src="flagUrl(furthest.location.country_code)"
            class="fp-flag"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.furthest {
  margin: 0 3rem;
  padding: 0.625rem 0.75rem;
  border-left: 3px solid var(--fp-accent);
  background: color-mix(
    in srgb,
    var(--fp-accent) 6%,
    var(--page-bg, var(--bg))
  );
  border-radius: 0.375rem;
  --fp-accent: #00897b;
  z-index: 1;
}

.fp-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.fp-tag {
  font-size: 0.5625rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--fp-accent);
}

.fp-top-icon {
  color: var(--fp-accent);
  opacity: 0.6;
  font-variation-settings: "FILL" 0;
}

.fp-body {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.25rem;
}

/* ── Endpoints ────────────────────────── */

.fp-info {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.fp-info.right {
  text-align: right;
  align-items: flex-end;
}

.fp-name {
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--text-bright);
  line-height: 1.2;
}

.fp-sub {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.5625rem;
  color: var(--text-muted);
}

.fp-flag {
  width: 0.875rem;
  height: 0.625rem;
  border-radius: 1px;
  flex-shrink: 0;
}

.fp-sep {
  opacity: 0.4;
}

/* ── Trail ────────────────────────────── */

.fp-trail {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 0.375rem;
  min-width: 0;
}

.fp-line {
  flex: 1;
  border-top: 1.5px dashed color-mix(in srgb, var(--fp-accent) 40%, transparent);
}

.fp-badge {
  display: flex;
  justify-content: center;
  gap: 0.2rem;
  background: color-mix(
    in srgb,
    var(--fp-accent) 12%,
    var(--page-bg, var(--bg))
  );
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
}

.fp-dist {
  font-size: 1.25rem;
  font-weight: 800;
  color: var(--text-bright);
}

.fp-unit {
  font-size: 0.5rem;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
}
</style>
