<script lang="ts" setup>
import { mediaThumbUrl } from "@/utils/media";
import { ref } from "vue";
import { matExpandMore } from "@quasar/extras/material-icons";

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
  <div class="picker">
    <button class="picker-pill" @click="open = !open">
      <span>{{ label }}</span>
      <q-icon
        :name="matExpandMore"
        size="1.125rem"
        class="pill-chevron"
        :class="{ rotated: open }"
      />
    </button>

    <div v-show="open" class="picker-panel">
      <div v-if="photos.length === 0" class="picker-empty">
        No landscape photos available
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
  position: relative;
  width: max-content;
}

.picker-pill {
  all: unset;
  cursor: pointer;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.3rem 0.625rem;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.55);
  color: rgba(255, 255, 255, 0.9);
  font-size: 0.875rem;
  font-weight: 600;
  white-space: nowrap;
  backdrop-filter: blur(8px);
  transition:
    background-color 0.15s ease,
    color 0.15s ease;

  &:hover {
    background: rgba(0, 0, 0, 0.7);
    color: white;
  }
}

.pill-chevron {
  transition: transform 0.2s ease;

  &.rotated {
    transform: rotate(180deg);
  }
}

.picker-panel {
  position: absolute;
  top: 100%;
  left: 0;
  margin-top: 0.25rem;
  width: 24rem;
  border-radius: 0.5rem;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(12px);
  overflow: hidden;
  z-index: 10;
}

.picker-empty {
  padding: 0.75rem 1rem;
  font-size: 0.6875rem;
  color: rgba(255, 255, 255, 0.5);
  text-align: center;
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
  aspect-ratio: 297 / 210;
  border-radius: 0.1875rem;
  overflow: hidden;
  outline: 2px solid transparent;
  outline-offset: -2px;
  transition: outline-color 0.15s ease;

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
