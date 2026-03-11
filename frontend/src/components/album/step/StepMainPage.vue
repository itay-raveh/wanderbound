<script lang="ts" setup>
import type { Step } from "@/client";
import type { DescriptionType } from "@/composables/usePageDescription";
import { usePrintMode } from "@/composables/usePrintReady";
import { useUserQuery } from "@/queries/useUserQuery";
import { mediaUrl } from "@/utils/media";
import { chooseTextDir } from "@/utils/text";
import { computed } from "vue";

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;

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
  () => props.descriptionType === "long" || props.descriptionType === "extra-long",
);

const printMode = usePrintMode();
const imgLoading = computed(() => (printMode ? "eager" : "lazy"));

const countryMapUrl = computed(() => {
  const { lat, lon } = props.step.location;
  const raw = props.colors[props.step.location.country_code];
  const color = (typeof raw === "string" ? raw : "#FF0000").replace("#", "");
  return `https://api.mapbox.com/styles/v1/mapbox/dark-v11/static/pin-s+${color}(${lon},${lat})/${lon},${lat},4,0/160x160@2x?access_token=${MAPBOX_TOKEN}`;
});

const { formatTemp, formatElevation, formatDate, isKm } = useUserQuery();

function weatherIconUrl(iconName: string): string {
  return `https://basmilius.github.io/weather-icons/production/fill/all/${iconName}.svg`;
}
</script>

<template>
  <div :class="{ 'with-long-desc': isLongDesc }" class="page-container">
    <div class="data">
      <div>
        <div class="map-coords-container">
          <div class="map-icon">
            <img
              :src="countryMapUrl"
              :alt="step.location.country_code"
              :loading="imgLoading"
              class="country-map-img"
            />
          </div>
          <div v-if="step.location" class="coordinates">
            {{ step.location.lat.toFixed(4) }}&deg; N<br />{{
              step.location.lon.toFixed(4)
            }}&deg; E
          </div>
        </div>
        <div class="country">
          <q-img
            :src="`https://flagcdn.com/${step.location.country_code}.svg`"
            class="country-flag"
          />
          {{ step.location.detail }}
        </div>
        <div class="name">{{ step.name }}</div>
      </div>

      <div
        v-if="!isLongDesc && mainPageText"
        :dir="chooseTextDir(mainPageText)"
        class="description short"
      >
        {{ mainPageText }}
      </div>

      <div class="metadata-section">
        <div class="metadata">
          <div class="metadata-item">
            <div class="metadata-label">
              {{ formatDate(new Date(step.datetime), { month: "long" }) }}
            </div>
            <div class="metadata-value">
              {{ formatDate(new Date(step.datetime), { day: "numeric" }) }}
            </div>
          </div>
          <div class="metadata-item">
            <div v-if="step.weather.night" class="metadata-label">
              <q-icon
                :src="weatherIconUrl(step.weather.night.icon)"
                class="weather-icon"
              />
              {{ formatTemp(step.weather.night.temp) }}
            </div>
            <div class="metadata-value">
              <q-icon
                :src="weatherIconUrl(step.weather.day.icon)"
                class="weather-icon"
              />
              {{ formatTemp(step.weather.day.temp) }}
            </div>
          </div>
          <div class="metadata-item">
            <div class="metadata-label">{{ isKm ? 'm.a.s.l' : 'ft a.s.l' }}</div>
            <div class="metadata-value">
              {{ formatElevation(step.elevation) }}
            </div>
          </div>
        </div>

        <div class="progress-container">
          <div class="progress-bar">
            <div
              :style="`width: ${step.idx}%; background: ${colors[step.location.country_code]}`"
              class="progress-fill"
            ></div>
          </div>
          <div
            :style="`border-bottom-color: ${colors[step.location.country_code]}; left: ${step.idx}%; transform: translateX(-55%)`"
            class="counter-arrow"
          ></div>
          <div
            :style="`left: ${step.idx}%; transform: translateX(-55%)`"
            class="counter-wrapper"
          >
            <div
              :style="`background: ${colors[step.location.country_code]}`"
              class="counter"
            >
              STEP {{ step.idx }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="content">
      <div
        v-if="isLongDesc && mainPageText"
        :dir="chooseTextDir(mainPageText)"
        class="description long"
      >
        {{ mainPageText }}
      </div>
      <q-img
        v-else-if="step.cover"
        :src="mediaUrl(step.cover)"
        :loading="imgLoading"
        class="main-image cover-photo"
      />
      <div
        v-else
        class="main-image cover-photo flex flex-center"
        style="min-height: 100%; width: 100%; background: var(--bg-secondary)"
      >
        <span style="color: var(--text-muted)">Drop Step Cover</span>
      </div>
    </div>

    <div class="step-index">{{ step.idx }}</div>
  </div>
</template>

<style lang="scss" scoped>
.data {
  flex: 1;
  background: var(--bg);
  color: var(--text);
  padding: 3rem 1.5rem 3rem 4rem;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.content {
  flex: 1;
  aspect-ratio: 1 / 1.414;
  display: flex;
  min-height: 100%;
  background-color: var(--bg);
}

.main-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.page.with-long-desc {
  flex-direction: column;
}

.page.with-long-desc .data {
  flex-direction: row;
  align-items: center;
  padding: 4rem 4rem 1.5rem 4rem;
}

.page.with-long-desc .metadata-section {
  width: 45%;
}

.page.with-long-desc .content {
  width: 100%;
  min-height: 300px;
  background: var(--bg);
}

/* Location & Metadata Components */
.map-coords-container {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.coordinates {
  color: var(--text-muted);
}

.country {
  text-transform: uppercase;
  margin-bottom: 0.5rem;
}

.country-flag {
  width: 24px;
  height: 18px;
}

.metadata {
  display: flex;
  justify-content: space-between;
  margin-bottom: 1.25rem;
}

.metadata-item {
  display: flex;
  flex-direction: column;
}

.metadata-label {
  font-size: 0.8rem;
  text-transform: uppercase;
  color: var(--text-muted);
  margin-bottom: 0.5rem;
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.weather-icon {
  width: 1.5rem;
  height: 1.5rem;
  flex-shrink: 0;
  object-fit: contain;
  margin-right: 0.125rem;
}

.metadata-value {
  font-size: 1.4rem;
  font-weight: bold;
  color: var(--text);
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.metadata-item:nth-child(2) .metadata-value {
  justify-content: center;
}

.metadata-item:last-child .metadata-value {
  justify-content: flex-end;
}

.metadata-value .weather-icon {
  width: 2rem;
  height: 2rem;
  flex-shrink: 0;
  object-fit: contain;
}

/* Progress Bar */
.progress-container {
  position: relative;
  margin-bottom: 1.5rem;
}

.progress-bar {
  width: 100%;
  height: 3px;
  background: color-mix(in srgb, var(--text) 10%, transparent);
}

.progress-fill {
  height: 100%;
  position: relative;
  background-color: var(--q-primary);
}

.counter-wrapper {
  position: absolute;
  top: 13px;
}

.counter-arrow {
  width: 0;
  height: 0;
  border-left: 6px solid transparent;
  border-right: 6px solid transparent;
  border-bottom: 6px solid var(--q-primary);
  position: relative;
  top: 4px;
}

.counter {
  width: max-content;
  font-size: 0.75rem;
  font-weight: bold;
  color: white;
  padding: 4px 12px;
  border-radius: 1px;
  background-color: var(--q-primary);
}

/* Typography */
.name {
  font-size: 1.3rem;
  font-weight: bold;
  text-transform: uppercase;
}

.description {
  width: 100%;
  font-size: 0.9rem;
  color: var(--text-muted);
  white-space: pre-wrap;
  text-align: justify;
}

.description.short {
  margin-bottom: 2rem;
  margin-top: 2rem;
  overflow: hidden;
}

.description.long {
  font-size: 1rem;
  padding: 3rem 1.5rem;
  column-width: 30rem;
  column-fill: auto;
  column-gap: 3rem;
}

/* Map mini-icon in step data panel */
.map-icon {
  width: 5rem;
  height: 5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: 4px;
}
.country-map-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

// Step Index
.step-index {
  position: absolute;
  top: 0;
  left: -4rem;
  font-size: 4rem;
  color: var(--text-muted);
}

</style>
