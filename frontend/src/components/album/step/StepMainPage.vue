<script lang="ts" setup>
import type { Step } from "@/client";
import type { DescriptionType } from "@/composables/usePageDescription";
import { usePrintMode } from "@/composables/usePrintReady";
import { useUserQuery } from "@/queries/useUserQuery";
import { mediaUrl } from "@/utils/media";
import { chooseTextDir } from "@/utils/text";
import { computed } from "vue";
import CountrySilhouette from "./CountrySilhouette.vue";

const props = defineProps<{
  colors: Record<string, string>;
  step: Step;
  descriptionType: DescriptionType;
  mainPageText: string;
}>();

defineEmits<{
  "update:cover": [path: string];
}>();

const isLongDesc = computed(
  () =>
    props.descriptionType === "long" ||
    props.descriptionType === "extra-long",
);

const printMode = usePrintMode();
const imgLoading = computed(() => (printMode ? "eager" : "lazy"));

const { formatTemp, formatElevation, formatDate, isKm } = useUserQuery();

const countryColor = computed(() => {
  const raw = props.colors[props.step.location.country_code];
  return typeof raw === "string" ? raw : "#4A90D9";
});

const dateStr = computed(() => {
  const d = new Date(props.step.datetime);
  return {
    day: formatDate(d, { day: "numeric" }),
    month: formatDate(d, { month: "long" }),
    year: formatDate(d, { year: "numeric" }),
  };
});

function weatherIconUrl(iconName: string): string {
  return `https://basmilius.github.io/weather-icons/production/fill/all/${iconName}.svg`;
}
</script>

<template>
  <div :class="{ 'long-desc': isLongDesc }" class="page-container step-main">
    <!-- LEFT: Metadata Panel -->
    <div class="meta-panel">
      <div class="meta-top">
        <!-- Country silhouette + location -->
        <div class="location-block">
          <div class="silhouette-box">
            <CountrySilhouette
              :country-code="step.location.country_code"
              :lat="step.location.lat"
              :lon="step.location.lon"
              :color="countryColor"
            />
          </div>
          <div class="location-text">
            <div class="country-row">
              <q-img
                :src="`https://flagcdn.com/${step.location.country_code}.svg`"
                class="flag"
              />
              <span class="country-name">{{ step.location.detail }}</span>
            </div>
            <h2 class="step-name">{{ step.name }}</h2>
          </div>
        </div>

        <!-- Date -->
        <div class="date-block">
          <span class="date-day">{{ dateStr.day }}</span>
          <div class="date-rest">
            <span class="date-month">{{ dateStr.month }}</span>
            <span class="date-year">{{ dateStr.year }}</span>
          </div>
        </div>

        <!-- Stats row -->
        <div class="stats-row">
          <div v-if="step.weather?.day" class="stat-item">
            <q-icon
              :src="weatherIconUrl(step.weather.day.icon)"
              class="weather-icon"
            />
            <span class="stat-value">{{
              formatTemp(step.weather.day.temp)
            }}</span>
          </div>
          <div v-if="step.weather?.night" class="stat-item stat-night">
            <q-icon
              :src="weatherIconUrl(step.weather.night.icon)"
              class="weather-icon night"
            />
            <span class="stat-value muted">{{
              formatTemp(step.weather.night.temp)
            }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">{{ isKm ? "m.a.s.l" : "ft a.s.l" }}</span>
            <span class="stat-value">{{
              formatElevation(step.elevation)
            }}</span>
          </div>
        </div>
      </div>

      <!-- Short description (when not long) -->
      <div
        v-if="!isLongDesc && mainPageText"
        :dir="chooseTextDir(mainPageText)"
        class="description"
      >
        {{ mainPageText }}
      </div>

      <!-- Progress bar -->
      <div class="progress-section">
        <div class="progress-track">
          <div
            :style="{
              width: `${Math.min(step.idx, 100)}%`,
              background: countryColor,
            }"
            class="progress-fill"
          />
        </div>
        <div
          :style="{
            left: `${Math.min(step.idx, 100)}%`,
            transform: 'translateX(-50%)',
          }"
          class="step-badge-wrapper"
        >
          <div class="step-badge-arrow" :style="{ borderBottomColor: countryColor }" />
          <div :style="{ background: countryColor }" class="step-badge">
            STEP {{ step.idx }}
          </div>
        </div>
      </div>
    </div>

    <!-- RIGHT: Cover Photo or Long Description -->
    <div class="content-panel">
      <div
        v-if="isLongDesc && mainPageText"
        :dir="chooseTextDir(mainPageText)"
        class="description-full"
      >
        {{ mainPageText }}
      </div>
      <q-img
        v-else-if="step.cover"
        :src="mediaUrl(step.cover)"
        :loading="imgLoading"
        class="cover-photo"
      />
      <div v-else class="cover-placeholder">
        <span>Drop Step Cover</span>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.step-main {
  display: flex;
  background: var(--bg);
  color: var(--text);
  overflow: hidden;
}

// ─── Meta Panel (left side) ───
.meta-panel {
  flex: 0 0 42%;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 2.5rem 2rem 1.5rem 3rem;
  position: relative;
}

.meta-top {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

// ─── Location Block ───
.location-block {
  display: flex;
  gap: 1.25rem;
  align-items: flex-start;
}

.silhouette-box {
  width: 6rem;
  height: 6rem;
  flex-shrink: 0;
  opacity: 0.7;
}

.location-text {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 0;
}

.country-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
}

.flag {
  width: 1.25rem;
  height: 0.9rem;
  flex-shrink: 0;
  border-radius: 1px;
}

.step-name {
  font-size: 1.6rem;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: -0.01em;
  line-height: 1.15;
  margin: 0;
  color: var(--text-bright);
}

// ─── Date Block ───
.date-block {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
}

.date-day {
  font-size: 2.5rem;
  font-weight: 800;
  line-height: 1;
  color: var(--text-bright);
}

.date-rest {
  display: flex;
  flex-direction: column;
}

.date-month {
  font-size: 0.85rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text);
}

.date-year {
  font-size: 0.75rem;
  color: var(--text-muted);
}

// ─── Stats Row ───
.stats-row {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  flex-wrap: wrap;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.stat-label {
  font-size: 0.65rem;
  text-transform: uppercase;
  color: var(--text-faint);
  letter-spacing: 0.03em;
}

.stat-value {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--text);
}

.stat-value.muted {
  color: var(--text-muted);
  font-weight: 500;
}

.weather-icon {
  width: 1.75rem;
  height: 1.75rem;
  flex-shrink: 0;
}

.weather-icon.night {
  width: 1.4rem;
  height: 1.4rem;
  opacity: 0.6;
}

// ─── Description ───
.description {
  font-size: 0.85rem;
  line-height: 1.6;
  color: var(--text-muted);
  white-space: pre-wrap;
  text-align: justify;
  overflow: hidden;
  flex: 1;
  margin: 0.5rem 0;
}

// ─── Progress Section ───
.progress-section {
  position: relative;
  margin-top: auto;
  padding-top: 1rem;
}

.progress-track {
  width: 100%;
  height: 2px;
  background: color-mix(in srgb, var(--text) 10%, transparent);
}

.progress-fill {
  height: 100%;
}

.step-badge-wrapper {
  position: absolute;
  top: calc(1rem + 2px);
  display: flex;
  flex-direction: column;
  align-items: center;
}

.step-badge-arrow {
  width: 0;
  height: 0;
  border-left: 5px solid transparent;
  border-right: 5px solid transparent;
  border-bottom: 5px solid;
}

.step-badge {
  font-size: 0.65rem;
  font-weight: 700;
  color: white;
  padding: 0.2rem 0.6rem;
  white-space: nowrap;
  letter-spacing: 0.04em;
}

// ─── Content Panel (right side) ───
.content-panel {
  flex: 1;
  display: flex;
  min-height: 0;
}

.cover-photo {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.cover-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-secondary);
  color: var(--text-faint);
  font-size: 0.85rem;
}

// ─── Long Description Layout ───
.description-full {
  padding: 2.5rem 3rem;
  font-size: 0.95rem;
  line-height: 1.65;
  color: var(--text-muted);
  white-space: pre-wrap;
  text-align: justify;
  column-width: 28rem;
  column-fill: auto;
  column-gap: 2.5rem;
  overflow: hidden;
}

// ─── Long Description Adjustments ───
.step-main.long-desc {
  flex-direction: column;

  .meta-panel {
    flex: 0 0 auto;
    flex-direction: row;
    align-items: center;
    gap: 2rem;
    padding: 2rem 3rem 1rem;
  }

  .meta-top {
    flex: 1;
    flex-direction: row;
    align-items: center;
    gap: 2rem;
  }

  .location-block {
    flex: 0 0 auto;
  }

  .silhouette-box {
    width: 4rem;
    height: 4rem;
  }

  .step-name {
    font-size: 1.2rem;
  }

  .date-block {
    flex: 0 0 auto;
  }

  .date-day {
    font-size: 1.8rem;
  }

  .stats-row {
    flex: 0 0 auto;
  }

  .description {
    display: none;
  }

  .progress-section {
    flex: 0 0 auto;
    width: 12rem;
    padding-top: 0;
  }

  .content-panel {
    flex: 1;
    min-height: 0;
  }
}
</style>
