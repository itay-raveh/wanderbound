<script lang="ts" setup>
import type { Step } from "@/client";
import type { JustifiedLine } from "@/composables/useTextLayout";
import { useUserQuery } from "@/queries/useUserQuery";
import EditableText from "../EditableText.vue";
import { getCountryColor, CONTRAST_TEXT_DARK, CONTRAST_TEXT_LIGHT } from "../colors";
import { daysBetween, parseLocalDate } from "@/utils/date";
import { flagUrl, weatherIconUrl } from "@/utils/media";
import { colors as qColors, Dark } from "quasar";
import { useI18n } from "vue-i18n";
import { computed } from "vue";
import CountryPinMap from "./CountryPinMap.vue";
import { useAlbum } from "@/composables/useAlbum";

const props = defineProps<{
  step: Step;
  sidebarLines?: JustifiedLine[];
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

const badgeTextColor = computed(() =>
  qColors.brightness(countryColor.value) > 128 ? CONTRAST_TEXT_DARK : CONTRAST_TEXT_LIGHT,
);

/** Derive alt text from Basmilius weather icon names (e.g. "partly-cloudy-day" → "partly cloudy"). */
function weatherAlt(icon: string): string {
  return icon.replace(/-day|-night/g, "").replace(/-/g, " ");
}

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
  <div class="meta-panel">
    <!-- Country silhouette + coordinates -->
    <div class="silhouette-row">
      <div class="silhouette-box">
        <CountryPinMap
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

    <!-- Description text (clipped by overflow: hidden when it exceeds sidebar height) -->
    <EditableText
      :model-value="step.description ?? ''"
      multiline
      :placeholder="t('album.descriptionPlaceholder')"
      dir="auto"
      class="description"
      :lines="sidebarLines"
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
          <div v-if="step.weather?.night" class="weather-row">
            <img
              :src="weatherIconUrl(step.weather.night.icon)"
              class="weather-icon-sm"
              :alt="weatherAlt(step.weather.night.icon)"
            />
            <span class="stat-label text-muted">{{
              formatTemp(step.weather.night.temp)
            }}</span>
          </div>
          <div class="weather-row">
            <img
              :src="weatherIconUrl(step.weather.day.icon)"
              class="weather-icon-lg"
              :alt="weatherAlt(step.weather.day.icon)"
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
        role="progressbar"
        :aria-valuenow="dayNumber"
        aria-valuemin="1"
        :aria-valuemax="totalDays"
        :aria-label="t('album.day', { n: dayNumber })"
        :style="{ '--progress': `${progressPercent}%` }"
      >
        <div class="progress-track">
          <div
            :style="{ width: `${progressPercent}%` }"
            class="progress-fill"
          />
        </div>
        <div class="badge-rail">
          <div class="badge-group">
            <div class="badge-arrow" />
            <div class="step-badge">{{ t("album.day", { n: dayNumber }) }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.meta-panel {
  display: flex;
  flex-direction: column;
  padding-block: var(--page-inset-y) 0;
  padding-inline: var(--page-inset-x) var(--page-inset-y);
  box-sizing: border-box;
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
}

.coords {
  display: flex;
  flex-direction: column;
  gap: var(--gap-xs);
  font-family: var(--font-mono);
  font-size: var(--type-sm);
  font-weight: 400;
  font-variant-numeric: tabular-nums;
  letter-spacing: var(--tracking-mono);
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
  width: 1rem;
  height: calc(1rem * 2 / 3); /* 3:2 flag aspect ratio */
  flex-shrink: 0;
  border-radius: var(--radius-xs);
  object-fit: cover;
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
  font-family: var(--font-album-body);
  font-size: var(--type-xs);
  line-height: 1.65;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  text-align: justify;
  hyphens: auto;
  overflow: hidden;
  min-width: 0;
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
  font-size: var(--type-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
}

.stat-value {
  font-size: var(--type-xl);
  font-weight: 800;
  font-variant-numeric: tabular-nums;
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

.weather-icon-sm {
  width: 1rem;
  height: 1rem;
  flex-shrink: 0;
}

.weather-icon-lg {
  width: 1.375rem;
  height: 1.375rem;
  flex-shrink: 0;
}

// Progress bar is direction-independent - do not add rtl:ignore or direction overrides.
.progress-track {
  display: flex;
  width: 100%;
  height: 0.375rem;
  border-radius: var(--radius-xs);
  background: color-mix(in srgb, var(--text) 10%, transparent);
  overflow: hidden;
  print-color-adjust: exact;
}

.progress-fill {
  height: 100%;
  border-radius: var(--radius-xs);
  background: v-bind(countryColor);
  print-color-adjust: exact;
}

.badge-rail {
  position: relative;
  height: calc(0.375rem + 1.3rem);
  margin-top: var(--gap-sm);
}

.badge-group {
  position: absolute;
  top: 0;
  left: var(--progress);
  transform: translateX(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
}

.badge-arrow {
  width: 0;
  height: 0;
  border-left: 0.375rem solid transparent;
  border-right: 0.375rem solid transparent;
  border-bottom: 0.375rem solid v-bind(countryColor);
  print-color-adjust: exact;
}

.step-badge {
  margin-top: -0.0625rem;
  font-size: var(--type-xs);
  font-weight: 700;
  padding: var(--gap-xs) var(--gap-md);
  border-radius: var(--radius-xs);
  white-space: nowrap;
  letter-spacing: var(--tracking-wide);
  color: v-bind(badgeTextColor);
  background: v-bind(countryColor);
  print-color-adjust: exact;
}
</style>
