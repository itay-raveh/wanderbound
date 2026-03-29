<script lang="ts" setup>
import { mediaThumbUrl } from "@/utils/media";
import { useI18n } from "vue-i18n";
import { ref } from "vue";
import { matExpandMore } from "@quasar/extras/material-icons";

const { t } = useI18n();

defineProps<{
  modelValue: string;
  albumId: string;
  label: string;
  photos: string[];
}>();

const emit = defineEmits<{
  "update:modelValue": [name: string];
}>();

const open = ref(false);

function select(name: string) {
  emit("update:modelValue", name);
  open.value = false;
}
</script>

<template>
  <div class="picker relative-position" @keydown.escape="open = false">
    <button class="picker-pill" :aria-expanded="open" @click="open = !open">
      <span>{{ label }}</span>
      <q-icon
        :name="matExpandMore"
        size="1.125rem"
        class="pill-chevron"
        :class="{ rotated: open }"
      />
    </button>

    <div v-if="open" class="picker-backdrop" @click="open = false" />
    <div v-if="open" class="picker-panel overflow-hidden" role="listbox" :aria-label="label">
      <div v-if="photos.length === 0" class="picker-empty text-center">
        {{ t("album.noLandscapePhotos") }}
      </div>
      <div v-else class="picker-grid">
        <button
          v-for="(photo, idx) in photos"
          :key="photo"
          role="option"
          class="grid-cell"
          :class="{ selected: photo === modelValue }"
          :aria-selected="photo === modelValue"
          :aria-label="t('album.selectPhoto') + ` ${idx + 1}`"
          @click="select(photo)"
        >
          <img
            :src="mediaThumbUrl(photo, albumId)"
            loading="lazy"
            class="cell-img"
            alt=""
          >
        </button>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.picker {
  width: max-content;
}

.picker-pill {
  all: unset;
  cursor: pointer;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  gap: var(--gap-sm);
  padding: var(--gap-sm-md) var(--gap-md-lg);
  border-radius: var(--radius-full);
  background: rgba(0, 0, 0, 0.6);
  color: rgba(255, 255, 255, 0.9);
  font-size: var(--type-sm);
  font-weight: 600;
  white-space: nowrap;
  backdrop-filter: blur(10px);
  transition:
    background-color var(--duration-fast) ease,
    color var(--duration-fast) ease;

  &:hover {
    background: rgba(0, 0, 0, 0.75);
    color: white;
  }

  &:focus-visible {
    outline: 2px solid white;
    outline-offset: 2px;
  }
}

.pill-chevron {
  transition: transform var(--duration-fast) ease;

  &.rotated {
    transform: rotate(180deg);
  }
}

.picker-backdrop {
  position: fixed;
  inset: 0;
  z-index: 9;
}

.picker-panel {
  position: absolute;
  top: 100%;
  inset-inline-start: 0;
  margin-top: var(--gap-sm);
  width: 24rem;
  border-radius: var(--radius-md);
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(10px);
  z-index: 10;
}

.picker-empty {
  padding: var(--gap-md-lg) var(--gap-lg);
  font-size: var(--type-2xs);
  color: rgba(255, 255, 255, 0.5);
}

.picker-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  // CSS grid auto-rows ignores aspect-ratio when the container has overflow.
  // Derive row height from the column fraction: (width - gaps) / 3 * (210/297).
  grid-auto-rows: calc((24rem - 4 * var(--gap-xs)) / 3 * 210 / 297);
  gap: var(--gap-xs);
  padding: var(--gap-xs);
  max-height: 24rem;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.3) transparent;
}

.grid-cell {
  background: none;
  border: none;
  padding: 0;
  margin: 0;
  font: inherit;
  color: inherit;
  cursor: pointer;
  aspect-ratio: var(--page-aspect);
  border-radius: var(--radius-xs);
  overflow: hidden;
  outline: 2px solid transparent;
  outline-offset: -2px;
  transition: outline-color var(--duration-fast) ease;

  &.selected {
    outline-color: var(--q-primary);
  }

  &:hover:not(.selected) {
    outline-color: rgba(255, 255, 255, 0.5);
  }

  &:focus-visible {
    outline-color: var(--q-primary);
  }
}

.cell-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

@media (pointer: coarse) {
  .picker-pill {
    padding: var(--gap-md) var(--gap-lg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .picker-pill,
  .pill-chevron,
  .grid-cell {
    transition: none;
  }
}
</style>
