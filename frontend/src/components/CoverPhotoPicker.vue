<script lang="ts" setup>
import { mediaThumbUrl } from "@/utils/media";
import { computed, ref } from "vue";
import { matExpandMore } from "@quasar/extras/material-icons";

const props = defineProps<{
  modelValue: string;
  albumId: string;
  label: string;
  photos: string[];
}>();

const emit = defineEmits<{
  "update:modelValue": [name: string];
}>();

const open = ref(false);

const thumbUrl = computed(() =>
  props.modelValue ? mediaThumbUrl(props.modelValue, props.albumId) : "",
);

function select(name: string) {
  emit("update:modelValue", name);
  open.value = false;
}
</script>

<template>
  <div class="picker">
    <button class="picker-trigger" @click="open = !open">
      <q-img
        v-if="thumbUrl"
        :src="thumbUrl"
        class="trigger-thumb"
        fit="cover"
        no-spinner
      />
      <div v-else class="trigger-thumb trigger-empty" />
      <span class="trigger-label">{{ label }}</span>
      <q-icon
        :name="matExpandMore"
        size="1.125rem"
        class="trigger-chevron"
        :class="{ rotated: open }"
      />
    </button>

    <q-slide-transition>
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
            <q-img
              :src="mediaThumbUrl(photo, albumId)"
              fit="cover"
              loading="lazy"
              no-spinner
              class="cell-img"
            />
          </button>
        </div>
      </div>
    </q-slide-transition>
  </div>
</template>

<style lang="scss" scoped>
.picker {
  display: flex;
  flex-direction: column;
}

.picker-trigger {
  all: unset;
  cursor: pointer;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.375rem 0.5rem;
  border: 1px solid var(--border-color);
  border-radius: 0.375rem;
  transition: border-color 0.15s ease;

  &:hover {
    border-color: var(--text-faint);
  }
}

.trigger-thumb {
  width: 4rem;
  height: 3rem;
  border-radius: 0.25rem;
  flex-shrink: 0;
}

.trigger-empty {
  background: var(--surface);
}

.trigger-label {
  flex: 1;
  font-size: 0.8125rem;
  color: var(--text);
  text-align: left;
}

.trigger-chevron {
  color: var(--text-faint);
  transition: transform 0.2s ease;
  flex-shrink: 0;

  &.rotated {
    transform: rotate(180deg);
  }
}

.picker-panel {
  border: 1px solid var(--border-color);
  border-top: none;
  border-radius: 0 0 0.375rem 0.375rem;
  overflow: hidden;
}

.picker-empty {
  padding: 1rem;
  font-size: 0.75rem;
  color: var(--text-faint);
  text-align: center;
}

.picker-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.125rem;
  padding: 0.125rem;
  max-height: 14rem;
  overflow-y: auto;
}

.grid-cell {
  all: unset;
  cursor: pointer;
  aspect-ratio: 4 / 3;
  border-radius: 0.1875rem;
  overflow: hidden;
  outline: 2px solid transparent;
  outline-offset: -2px;
  transition: outline-color 0.15s ease;

  &.selected {
    outline-color: var(--q-primary);
  }

  &:hover:not(.selected) {
    outline-color: color-mix(in srgb, var(--q-primary) 50%, transparent);
  }
}

.cell-img {
  width: 100%;
  height: 100%;
}
</style>
