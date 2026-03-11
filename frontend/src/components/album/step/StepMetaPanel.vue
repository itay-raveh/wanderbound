<script lang="ts" setup>
import type { Step } from "@/client";
import type { DescriptionType } from "@/composables/usePageDescription";
import { useUserQuery } from "@/queries/useUserQuery";
import { flagUrl } from "@/utils/media";
import { chooseTextDir } from "@/utils/text";
import { weatherIconUrl } from "@/utils/weather";
import { Dark } from "quasar";
import { computed } from "vue";
import CountrySilhouette from "./CountrySilhouette.vue";

const props = defineProps<{
  step: Step;
  colors: Record<string, string>;
  tripStart: string;
  descriptionType: DescriptionType;
  mainPageText: string;
  compact?: boolean;
}>();

const { formatTemp, formatElevationValue, formatDate, isKm, locale } = useUserQuery();

// RTL direction based on locale (Hebrew, Arabic)
const dir = computed(() => {
  const lang = locale.value.split("-")[0];
  return lang === "he" || lang === "ar" ? "rtl" : "ltr";
});

const countryColor = computed(() => {
  const raw = props.colors[props.step.location.country_code];
  const hex = typeof raw === "string" ? raw : "#4A90D9";
  if (Dark.isActive) return hex;
  return adjustColor(hex, 50);
});

function adjustColor(hex: string, amount: number): string {
  const h = hex.replace("#", "");
  const r = Math.min(255, parseInt(h.substring(0, 2), 16) + amount);
  const g = Math.min(255, parseInt(h.substring(2, 4), 16) + amount);
  const b = Math.min(255, parseInt(h.substring(4, 6), 16) + amount);
  return `#${r.toString(16).padStart(2, "0")}${g.toString(16).padStart(2, "0")}${b.toString(16).padStart(2, "0")}`;
}

function toDMS(decimal: number, isLat: boolean): string {
  const abs = Math.abs(decimal);
  const d = Math.floor(abs);
  const mFull = (abs - d) * 60;
  const m = Math.floor(mFull);
  const s = Math.round((mFull - m) * 60);
  const hemisphere = isLat ? (decimal >= 0 ? "N" : "S") : (decimal >= 0 ? "E" : "W");
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
  const start = new Date(props.tripStart);
  const current = new Date(props.step.datetime);
  start.setHours(0, 0, 0, 0);
  current.setHours(0, 0, 0, 0);
  return Math.floor((current.getTime() - start.getTime()) / 86_400_000) + 1;
});

const progressPercent = computed(() => Math.min(dayNumber.value, 100));

const dateStr = computed(() => {
  const d = new Date(props.step.datetime);
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
      <div class="coords" dir="ltr">
        <span>{{ coords.lat }}</span>
        <span>{{ coords.lon }}</span>
      </div>
    </div>

    <!-- Country + Step name -->
    <div class="name-block">
      <div class="country-row">
        <q-img :src="flagUrl(step.location.country_code)" class="flag" />
        <span>{{ step.location.detail }}</span>
      </div>
      <h2 class="step-name">{{ step.name }}</h2>
    </div>

    <!-- Short description (normal layout only) -->
    <div
      v-if="!compact && mainPageText"
      :dir="chooseTextDir(mainPageText)"
      class="description"
    >
      {{ mainPageText }}
    </div>

    <!-- Bottom section: stats + progress -->
    <div class="bottom-section" :dir="dir">
      <div class="stats-bar">
        <!-- Date -->
        <div class="stat-col">
          <span class="stat-label">{{ dateStr.month }}</span>
          <span class="stat-value">{{ dateStr.day }}</span>
        </div>

        <!-- Weather -->
        <div v-if="step.weather?.day" class="stat-col weather-col">
          <div v-if="step.weather?.night" class="weather-row weather-night">
            <img :src="weatherIconUrl(step.weather.night.icon)" class="weather-icon-sm" alt="" />
            <span class="stat-label">{{ formatTemp(step.weather.night.temp) }}</span>
          </div>
          <div class="weather-row">
            <img :src="weatherIconUrl(step.weather.day.icon)" class="weather-icon-lg" alt="" />
            <span class="stat-value">{{ formatTemp(step.weather.day.temp) }}</span>
          </div>
        </div>

        <!-- Elevation -->
        <div class="stat-col">
          <span class="stat-label">{{ isKm ? "M.A.S.L" : "FT A.S.L" }}</span>
          <span class="stat-value">{{ formatElevationValue(step.elevation) }}</span>
        </div>
      </div>

      <!-- Progress bar with day badge -->
      <div class="progress-section">
        <div class="progress-track">
          <div :style="{ width: `${progressPercent}%` }" class="progress-fill" />
        </div>
        <div class="badge-wrap">
          <div class="badge-arrow" />
          <div class="step-badge">DAY {{ dayNumber }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.meta-panel {
  display: flex;
  flex-direction: column;
  padding: 2.5rem 2.5rem 0 3rem;
}

// ─── Silhouette + Coords ───
.silhouette-row {
  display: flex;
  gap: 1rem;
  align-items: flex-start;
  margin-bottom: 1rem;
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
  gap: 0.15rem;
  font-family: "JetBrains Mono", "Fira Code", "SF Mono", "Cascadia Code", ui-monospace, monospace;
  font-size: 0.65rem;
  font-weight: 500;
  color: var(--text-muted);
  letter-spacing: 0.02em;
  padding-top: 0.25rem;
  white-space: pre;
}

// ─── Name Block ───
.name-block {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  margin-bottom: 0.75rem;
}

.country-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
}

.flag {
  width: 1.15rem;
  height: 0.8rem;
  flex-shrink: 0;
  border-radius: 1px;
}

.step-name {
  font-size: 1.35rem;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: -0.01em;
  line-height: 1.15;
  margin: 0;
  color: var(--text-bright);
}

// ─── Description ───
.description {
  font-size: 0.75rem;
  line-height: 1.65;
  color: var(--text);
  white-space: pre-wrap;
  text-align: justify;
  overflow: hidden;
  flex: 1;
  margin-bottom: 0.75rem;
}

// ─── Bottom Section ───
.bottom-section {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding-bottom: 2rem;
}

// ─── Stats Bar ───
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
  font-size: 0.6rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
}

.stat-value {
  font-size: 1.3rem;
  font-weight: 800;
  line-height: 1.1;
  letter-spacing: -0.02em;
  color: var(--text-bright);
}

// ─── Weather ───
.weather-col {
  gap: 0;
}

.weather-row {
  display: flex;
  align-items: center;
  gap: 0.25rem;
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

// ─── Progress Section ───
.progress-section {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.progress-track {
  width: 100%;
  height: 4px;
  border-radius: 2px;
  background: color-mix(in srgb, var(--text) 10%, transparent);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 2px;
  background: v-bind(countryColor);
}

.badge-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-top: 0.25rem;
}

.badge-arrow {
  width: 0;
  height: 0;
  border-left: 5px solid transparent;
  border-right: 5px solid transparent;
  border-bottom: 5px solid v-bind(countryColor);
}

.step-badge {
  font-size: 0.55rem;
  font-weight: 700;
  color: var(--text-bright);
  padding: 0.15rem 0.5rem;
  border-radius: 2px;
  white-space: nowrap;
  letter-spacing: 0.06em;
  background: v-bind(countryColor);
}

// ─── Compact (long-desc) Mode ───
.meta-panel.compact {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: auto auto;
  grid-template-areas:
    "sil   stats"
    "name  stats";
  column-gap: 1.5rem;
  padding: 2rem 3rem 1.25rem;

  .silhouette-row {
    grid-area: sil;
    margin-bottom: 0.5rem;
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
    font-size: 1.25rem;
  }

  .description {
    display: none;
  }

  .bottom-section {
    grid-area: stats;
    align-self: center;
    margin-top: 0;
    padding-bottom: 0;
    gap: 0.4rem;
  }
}
</style>
