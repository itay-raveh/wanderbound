<script lang="ts" setup>
import type { Step } from "@/client";
import type { DescriptionType } from "@/composables/useTextMeasure";
import { useUserQuery } from "@/queries/useUserQuery";
import EditableText from "../EditableText.vue";
import { getCountryColor } from "../colors";
import { daysBetween, parseLocalDate } from "@/utils/date";
import { flagUrl, weatherIconUrl } from "@/utils/media";
import { colors as qColors, Dark } from "quasar";
import { useI18n } from "vue-i18n";
import { computed } from "vue";
import CountrySilhouette from "./CountrySilhouette.vue";
import { useAlbum } from "@/composables/useAlbum";

const props = defineProps<{
  step: Step;
  descriptionType: DescriptionType;
  mainPageText: string;
  compact?: boolean;
}>();

const emit = defineEmits<{
  "update:name": [name: string];
  "update:description": [description: string];
}>();

const { colors, tripStart, totalDays } = useAlbum();

const { formatTemp, formatElevationValue, formatDate, isKm, countryName } =
  useUserQuery();
const { t } = useI18n();

const countryColor = computed(() => {
  const hex = getCountryColor(colors.value, props.step.location.country_code);
  return qColors.lighten(hex, Dark.isActive ? -20 : 20);
});

function toDMS(decimal: number, isLat: boolean): string {
  const abs = Math.abs(decimal);
  const d = Math.floor(abs);
  const mFull = (abs - d) * 60;
  const m = Math.floor(mFull);
  const s = Math.round((mFull - m) * 60);
  const hemisphere = isLat
    ? decimal >= 0
      ? "N"
      : "S"
    : decimal >= 0
      ? "E"
      : "W";
  const dStr = String(d).padStart(3, " ");
  const mStr = String(m).padStart(2, " ");
  const sStr = String(s).padStart(2, " ");
  return `${dStr}° ${mStr}' ${sStr}" ${hemisphere}`;
}

const coords = computed(() => ({
  lat: toDMS(props.step.location.lat, true),
  lon: toDMS(props.step.location.lon, false),
}));

const dayNumber = computed(() => {
  const start = parseLocalDate(tripStart.value);
  const current = parseLocalDate(props.step.datetime);
  return daysBetween(start, current) + 1;
});

const progressPercent = computed(() =>
  Math.min(100, Math.round((dayNumber.value / totalDays.value) * 100)),
);

const dateStr = computed(() => {
  const d = parseLocalDate(props.step.datetime);
  return {
    day: formatDate(d, { day: "numeric" }),
    month: formatDate(d, { month: "long" }),
  };
});
</script>

<template>
  <div :class="{ compact }" class="meta-panel">
    <!-- Country silhouette + coordinates -->
    <div class="silhouette-row">
      <div class="silhouette-box">
        <CountrySilhouette
          :country-code="step.location.country_code"
          :lat="step.location.lat"
          :lon="step.location.lon"
          :color="countryColor"
        />
      </div>
      <div class="coords text-muted" dir="ltr">
        <span>{{ coords.lat }}</span>
        <span>{{ coords.lon }}</span>
      </div>
    </div>

    <!-- Country + Step name -->
    <div class="name-block">
      <div class="country-row text-muted">
        <img :src="flagUrl(step.location.country_code)" class="flag" alt="" />
        <span>{{ countryName(step.location.country_code, step.location.detail) }}</span>
      </div>
      <EditableText
        :model-value="step.name"
        :placeholder="t('album.stepNamePlaceholder')"
        class="step-name text-bright"
        @update:model-value="emit('update:name', $event)"
      />
    </div>

    <!-- Short description (normal layout only) -->
    <EditableText
      v-if="!compact"
      :model-value="step.description ?? ''"
      multiline
      :placeholder="t('album.descriptionPlaceholder')"
      dir="auto"
      class="description"
      :display-value="mainPageText"
      @update:model-value="emit('update:description', $event)"
    />

    <!-- Bottom section: stats + progress -->
    <div class="bottom-section">
      <div class="stats-bar">
        <!-- Date -->
        <div class="stat-col">
          <span class="stat-label text-muted">{{ dateStr.month }}</span>
          <span class="stat-value text-bright">{{ dateStr.day }}</span>
        </div>

        <!-- Weather -->
        <div v-if="step.weather?.day" class="stat-col weather-col">
          <div v-if="step.weather?.night" class="weather-row weather-night">
            <img
              :src="weatherIconUrl(step.weather.night.icon)"
              class="weather-icon-sm"
              alt=""
            />
            <span class="stat-label text-muted">{{
              formatTemp(step.weather.night.temp)
            }}</span>
          </div>
          <div class="weather-row">
            <img
              :src="weatherIconUrl(step.weather.day.icon)"
              class="weather-icon-lg"
              alt=""
            />
            <span class="stat-value text-bright">{{
              formatTemp(step.weather.day.temp)
            }}</span>
          </div>
        </div>

        <!-- Elevation -->
        <div class="stat-col">
          <span class="stat-label text-muted">{{ isKm ? t("album.masl") : t("album.ftAsl") }}</span>
          <span class="stat-value text-bright">{{
            formatElevationValue(step.elevation)
          }}</span>
        </div>
      </div>

      <!-- Progress bar with day badge -->
      <div
        class="progress-section relative-position"
        :style="{ '--progress': `${progressPercent}%` }"
      >
        <div class="progress-track">
          <div
            :style="{ width: `${progressPercent}%` }"
            class="progress-fill"
          />
        </div>
        <div class="badge-rail">
          <div class="badge-arrow" />
          <div class="step-badge text-bright">{{ t("album.day", { n: dayNumber }) }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.meta-panel {
  display: flex;
  flex-direction: column;
  padding: var(--page-inset-y) var(--page-inset-y) 0 var(--page-inset-x);
}

.silhouette-row {
  display: flex;
  gap: var(--gap-lg);
  align-items: flex-start;
  margin-bottom: var(--gap-lg);
}

.silhouette-box {
  width: 5rem;
  height: 5rem;
  flex-shrink: 0;
  opacity: 0.85;
}

.coords {
  display: flex;
  flex-direction: column;
  gap: var(--gap-xs);
  font-family:
    "JetBrains Mono", "Fira Code", "SF Mono", "Cascadia Code", ui-monospace,
    monospace;
  font-size: var(--type-2xs);
  font-weight: 500;
  letter-spacing: 0.02em;
  padding-top: var(--gap-sm);
  white-space: pre;
}

.name-block {
  display: flex;
  flex-direction: column;
  gap: var(--gap-xs);
  margin-bottom: var(--gap-lg);
}

.country-row {
  display: flex;
  align-items: center;
  gap: var(--gap-md);
  font-size: var(--type-xs);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
}

.flag {
  width: 1.15rem;
  height: 0.8rem;
  flex-shrink: 0;
  border-radius: var(--radius-xs);
}

.step-name {
  font-size: var(--type-xl);
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: var(--tracking-tight);
  line-height: 1.15;
  margin: 0;
}

.description {
  font-size: var(--type-xs);
  line-height: 1.65;
  color: var(--text);
  white-space: pre-wrap;
  text-align: justify;
  overflow: hidden;
  flex: 1;
  margin-bottom: var(--gap-lg);
}

.bottom-section {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: var(--gap-md);
  padding-bottom: var(--page-inset-y);
}

.stats-bar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
}

.stat-col {
  display: flex;
  flex-direction: column;

  &:not(:first-child):not(:last-child) {
    align-items: center;
  }

  &:last-child {
    align-items: flex-end;
  }
}

.stat-label {
  font-size: var(--type-2xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
}

.stat-value {
  font-size: var(--type-xl);
  font-weight: 800;
  line-height: 1.1;
  letter-spacing: var(--tracking-tight);
}

.weather-col {
  gap: 0;
}

.weather-row {
  display: flex;
  align-items: center;
  gap: var(--gap-sm);
}

.weather-night {
  opacity: 0.7;
}

.weather-icon-sm {
  width: 1rem;
  height: 1rem;
  flex-shrink: 0;
}

.weather-icon-lg {
  width: 1.35rem;
  height: 1.35rem;
  flex-shrink: 0;
}

// Progress bar is direction-independent — do not add rtl:ignore or direction overrides.
.progress-track {
  display: flex;
  width: 100%;
  height: 4px;
  border-radius: var(--radius-xs);
  background: color-mix(in srgb, var(--text) 10%, transparent);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: var(--radius-xs);
  background: v-bind(countryColor);
}

.badge-rail {
  position: relative;
  width: 100%;
  // Reserve space: arrow (5px) + badge (~1rem)
  height: calc(5px + 1.1rem);
  margin-top: var(--gap-sm);
}

// Arrow + badge both clamped so the arrow never escapes the badge box.
// 5px = arrow half-width (border-left/right).
.badge-arrow {
  position: absolute;
  top: 0;
  left: clamp(5px, var(--progress), calc(100% - 5px));
  transform: translateX(-50%);
  width: 0;
  height: 0;
  border-left: 5px solid transparent;
  border-right: 5px solid transparent;
  border-bottom: 5px solid v-bind(countryColor);
}

// 1px overlap with arrow (top: 4px instead of 5px) prevents sub-pixel gaps.
.step-badge {
  --half-w: 1.75rem;
  position: absolute;
  top: 4px;
  left: clamp(
    0px,
    calc(var(--progress) - var(--half-w)),
    calc(100% - 2 * var(--half-w))
  );
  font-size: var(--type-3xs);
  font-weight: 700;
  padding: var(--gap-xs) var(--gap-md);
  border-radius: var(--radius-xs);
  white-space: nowrap;
  letter-spacing: var(--tracking-wide);
  background: v-bind(countryColor);
}

.meta-panel.compact {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: auto auto;
  grid-template-areas:
    "sil   stats"
    "name  stats";
  column-gap: 1.5rem;
  padding: 2rem var(--page-inset-x) 1.25rem;

  .silhouette-row {
    grid-area: sil;
    margin-bottom: var(--gap-md);
  }

  .silhouette-box {
    width: 4.5rem;
    height: 4.5rem;
  }

  .name-block {
    grid-area: name;
    align-self: end;
    margin-bottom: 0;
  }

  .step-name {
    font-size: var(--type-lg);
  }

  .description {
    display: none;
  }

  .bottom-section {
    grid-area: stats;
    align-self: center;
    margin-top: 0;
    padding-bottom: 0;
    gap: var(--gap-md);
  }
}
</style>
