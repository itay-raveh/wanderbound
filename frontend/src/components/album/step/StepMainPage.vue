<script lang="ts" setup>
import type { Album, Step } from "@/api";
import {
  clearDraggedPhoto,
  draggedPhoto,
  draggedSourceCallback,
} from "@/utils/dragState";
import { chooseTextDir } from "@/utils/text";
import { computed, ref } from "vue";

const props = defineProps<{
  album: Album;
  step: Step;
}>();

const emit = defineEmits<{
  "update:cover": [path: string];
}>();

const isLongDesc = computed(() => {
  return props.step.description.length > 500;
});

function weatherIconUrl(iconName: string): string {
  return `https://basmilius.github.io/weather-icons/production/fill/all/${iconName}.svg`;
}

const isDragOver = ref(false);

function onDropCover() {
  isDragOver.value = false;
  if (!draggedPhoto) return;

  emit("update:cover", draggedPhoto);
  if (draggedSourceCallback) draggedSourceCallback();
  clearDraggedPhoto();
}
</script>

<template>
  <div :class="{ 'with-long-desc': isLongDesc }" class="page-container">
    <div class="data">
      <div>
        <div class="map-coords-container">
          <div class="map-icon">
            <div class="map-svg-container">
              <q-icon
                :name="`svguse:countries/${step.location.country_code}.svg#map`"
                class="map"
                color="primary"
              >
              </q-icon>
              <div
                :style="`left: ${step.location.lat}%; top: ${step.location.lon}%; background: ${album.colors[step.location.country_code]}`"
                class="map-location-dot"
              />
            </div>
          </div>
          <div v-if="step.location" class="coordinates">
            {{ step.location.lat.toFixed(4) }}° N<br />{{
              step.location.lon.toFixed(4)
            }}° E
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
        v-if="!isLongDesc && step.description"
        :dir="chooseTextDir(step.description)"
        class="description short"
      >
        {{ step.description }}
      </div>

      <div class="metadata-section">
        <div class="metadata">
          <div class="metadata-item">
            <div class="metadata-label">
              {{
                new Date(step.datetime).toLocaleDateString("default", {
                  month: "long",
                })
              }}
            </div>
            <div class="metadata-value">
              {{
                new Date(step.datetime).toLocaleDateString("default", {
                  day: "numeric",
                })
              }}
            </div>
          </div>
          <div class="metadata-item">
            <div v-if="step.weather.night" class="metadata-label">
              <q-icon
                :src="weatherIconUrl(step.weather.night.icon)"
                class="weather-icon"
              />
              {{ Math.round(step.weather.night.temp) }}°
            </div>
            <div class="metadata-value">
              <q-icon
                :src="weatherIconUrl(step.weather.day.icon)"
                class="weather-icon"
              />
              {{ Math.round(step.weather.day.temp) }}°
            </div>
          </div>
          <div class="metadata-item">
            <div class="metadata-label">m.a.s.l</div>
            <div class="metadata-value">
              {{ Math.round(step.elevation) }}
            </div>
          </div>
        </div>

        <div class="progress-container">
          <div class="progress-bar">
            <div
              :style="`width: ${step.idx}%; background: ${album.colors[step.location.country_code]}`"
              class="progress-fill"
            ></div>
          </div>
          <div
            :style="`border-bottom-color: ${album.colors[step.location.country_code]}; left: ${step.idx}%; transform: translateX(-55%)`"
            class="counter-arrow"
          ></div>
          <div
            :style="`left: ${step.idx}%; transform: translateX(-55%)`"
            class="counter-wrapper"
          >
            <div
              :style="`background: ${album.colors[step.location.country_code]}`"
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
        v-if="isLongDesc && step.description"
        :dir="chooseTextDir(step.description)"
        class="description long"
      >
        {{ step.description }}
      </div>
      <q-img
        v-else-if="step.cover"
        :class="{ 'drag-over': isDragOver }"
        :src="`/api/v1/${step.cover}`"
        class="main-image cover-photo"
        @dragover.prevent="isDragOver = true"
        @dragleave.prevent="isDragOver = false"
        @drop.prevent="onDropCover"
      />
      <div
        v-else
        :class="{ 'drag-over': isDragOver }"
        class="main-image cover-photo flex flex-center bg-grey-3"
        style="min-height: 100%; width: 100%"
        @dragover.prevent="isDragOver = true"
        @dragleave.prevent="isDragOver = false"
        @drop.prevent="onDropCover"
      >
        <span>Drop Step Cover</span>
      </div>
    </div>

    <div class="step-index">{{ step.idx }}</div>
  </div>
</template>

<style lang="scss" scoped>
.data {
  flex: 1;
  background: var(--q-dark);
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
  background-color: var(--q-dark);
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
  background: var(--q-dark);
}

/* Location & Metadata Components */
.map-coords-container {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.coordinates {
  color: #9ca3af;
}

.country {
  font-family: inherit;
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
  color: #9ca3af;
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
  color: #e5e7eb;
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
  background: rgba(255, 255, 255, 0.1);
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
  color: #d1d5db;
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
}
.map-svg-container {
  position: relative;
}
.map-svg-container :deep(svg) {
  display: block;
  max-width: 5rem;
  max-height: 5rem;
  width: auto;
  height: auto;
}
/* Make SVG country outlines visible on dark backgrounds */
.map-svg-container :deep(svg path) {
  fill: rgba(255, 255, 255, 0.15);
  stroke: none;
}
.map-location-dot {
  position: absolute;
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  transform: translate(-50%, -50%);
  box-shadow:
    0 0.125rem 0.375rem rgba(0, 0, 0, 0.3),
    0 0 0.75rem currentColor;
}

// Step Index
.step-index {
  position: absolute;
  top: 0;
  left: -4rem;
  font-size: 4rem;
}

@media print {
  :deep(.map-svg-container svg path) {
    stroke: none !important;
  }
  .description {
    color: #333 !important;
  }
}
</style>
