<script lang="ts" setup>
import { type Location, type Step } from "@/client";
import { STAT_COLORS } from "@/utils/colors";
import { parseLocalDate } from "@/utils/date";
import { useUserQuery } from "@/queries/useUserQuery";
import { flagUrl } from "@/utils/media";
import distance from "@turf/distance";
import { point } from "@turf/helpers";
import { computed } from "vue";
import { matHome, matPlace } from "@quasar/extras/material-icons";

const props = defineProps<{
  home: Location;
  steps: Step[];
}>();

const { formatDistance, distanceUnit, formatDate } = useUserQuery();

const accentColor = STAT_COLORS.distance;

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

  const dateStr = formatDate(parseLocalDate(bestStep.datetime), {
    month: "short",
    day: "numeric",
  });
  return {
    location: bestStep.location,
    dist: formatDistance(maxDist),
    date: dateStr,
  };
});
</script>

<template>
  <div class="furthest">
    <div class="fp-top">
      <q-icon :name="matHome" size="1.375rem" class="fp-top-icon" />
      <q-icon :name="matPlace" size="1.375rem" class="fp-top-icon" />
    </div>

    <div class="fp-body">
      <!-- Home -->
      <div class="fp-info">
        <div class="fp-name text-bright">{{ home.name }}</div>
        <div class="fp-sub text-muted">
          <img
            :src="flagUrl(home.country_code)"
            class="fp-flag"
            loading="eager"
            alt=""
          >
          <span>{{ home.detail }}</span>
        </div>
      </div>

      <!-- Trail with distance badge -->
      <div class="fp-trail">
        <div class="fp-line" />
        <div class="column">
          <span class="fp-tag">Furthest from home</span>
          <div class="fp-badge">
            <span class="fp-dist text-bright">{{ furthest.dist }}</span>
            <span class="fp-unit text-muted">{{ distanceUnit() }}</span>
          </div>
        </div>
        <div class="fp-line" />
      </div>

      <!-- Furthest -->
      <div class="fp-info right">
        <div class="fp-name text-bright">{{ furthest.location.name }}</div>
        <div class="fp-sub text-muted">
          <span dir="auto">{{ furthest.date }}</span>
          <span class="fp-sep">·</span>
          <span>{{ furthest.location.detail }}</span>
          <img
            :src="flagUrl(furthest.location.country_code)"
            class="fp-flag"
            alt=""
          >
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.furthest {
  --fp-accent: v-bind(accentColor);
  margin: 0 var(--page-inset-x);
  padding: 0.625rem 0.75rem;
  border-left: 3px solid var(--fp-accent);
  background: color-mix(
    in srgb,
    var(--fp-accent) 6%,
    var(--page-bg, var(--bg))
  );
  border-radius: var(--radius-sm);
  z-index: 1;
}

.fp-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.fp-tag {
  font-size: var(--type-3xs);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
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
  gap: var(--gap-md);
  margin-top: var(--gap-sm);
}

.fp-info {
  display: flex;
  flex-direction: column;
  gap: var(--gap-xs);
}

.fp-info.right {
  text-align: right;
  align-items: flex-end;
}

.fp-name {
  font-size: var(--type-xs);
  font-weight: 700;
  line-height: 1.2;
}

.fp-sub {
  display: flex;
  align-items: center;
  gap: var(--gap-sm);
  font-size: var(--type-3xs);
}

.fp-flag {
  width: 0.875rem;
  height: 0.625rem;
  border-radius: var(--radius-xs);
  flex-shrink: 0;
}

.fp-sep {
  opacity: 0.4;
}

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
  border-radius: var(--radius-xs);
}

.fp-dist {
  font-size: var(--type-lg);
  font-weight: 800;
}

.fp-unit {
  font-size: var(--type-3xs);
  font-weight: 600;
  text-transform: uppercase;
}
</style>
