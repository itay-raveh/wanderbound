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
  <div class="picker relative-position">
    <button class="picker-pill" @click="open = !open">
      <span>{{ label }}</span>
      <q-icon
        :name="matExpandMore"
        size="1.125rem"
        class="pill-chevron"
        :class="{ rotated: open }"
      />
    </button>

    <div v-show="open" class="picker-panel overflow-hidden">
      <div v-if="photos.length === 0" class="picker-empty text-center">
        {{ t("album.noLandscapePhotos") }}
      </div>
      <div v-else class="picker-grid">
        <button
          v-for="photo in photos"
          :key="photo"
          class="grid-cell"
          :class="{ selected: photo === modelValue }"
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
  padding: 0.3rem 0.625rem;
  border-radius: var(--radius-full);
  background: rgba(0, 0, 0, 0.55);
  color: rgba(255, 255, 255, 0.9);
  font-size: var(--type-sm);
  font-weight: 600;
  white-space: nowrap;
  backdrop-filter: blur(8px);
  transition:
    background-color var(--duration-fast) ease,
    color var(--duration-fast) ease;

  &:hover {
    background: rgba(0, 0, 0, 0.7);
    color: white;
  }
}

.pill-chevron {
  transition: transform var(--duration-fast) ease;

  &.rotated {
    transform: rotate(180deg);
  }
}

.picker-panel {
  position: absolute;
  top: 100%;
  left: 0;
  margin-top: var(--gap-sm);
  width: 24rem;
  border-radius: var(--radius-md);
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(12px);
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
  gap: 3px;
  padding: 3px;
  max-height: 24rem;
  overflow-y: auto;
}

.grid-cell {
  all: unset;
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
}

.cell-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
</style>
