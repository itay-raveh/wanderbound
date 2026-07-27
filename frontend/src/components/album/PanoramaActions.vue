<script lang="ts" setup>
import { computed } from "vue";
import { useAlbum } from "@/composables/useAlbum";
import { t } from "@/i18n";
import { useDisablePanoramaMutation } from "@/queries/usePanoramaMutation";

const props = defineProps<{
  media: string;
  makeFullPage?: boolean;
  makePanoramaSpread?: boolean;
}>();

const emit = defineEmits<{
  frame: [];
  "make-full-page": [media: string];
  "make-panorama-spread": [media: string];
}>();

const { albumId, mediaByName } = useAlbum();
const disableMutation = useDisablePanoramaMutation();
const panorama = computed(() => mediaByName.value.get(props.media)?.panorama);
const disabling = computed(
  () => disableMutation.asyncStatus.value === "loading",
);

async function disablePanorama(): Promise<void> {
  if (disabling.value) return;
  await disableMutation.mutateAsync({
    aid: albumId.value,
    name: props.media,
  });
}
</script>

<template>
  <div class="panorama-actions" @click.stop>
    <button
      type="button"
      class="panorama-frame-action panorama-action"
      @click="emit('frame')"
    >
      {{ panorama ? t("panorama.frame.title") : t("panorama.treat") }}
    </button>
    <button
      v-if="panorama && makeFullPage"
      type="button"
      class="panorama-full-page-action panorama-action"
      @click="emit('make-full-page', media)"
    >
      {{ t("panorama.makeFullPage") }}
    </button>
    <button
      v-if="panorama && makePanoramaSpread"
      type="button"
      class="panorama-spread-action panorama-action"
      @click="emit('make-panorama-spread', media)"
    >
      {{ t("panorama.makeSpread") }}
    </button>
    <button
      v-if="panorama"
      type="button"
      class="panorama-disable-action panorama-action"
      :disabled="disabling"
      @click="disablePanorama"
    >
      {{ t("panorama.frame.disable") }}
    </button>
  </div>
</template>

<style lang="scss" scoped>
.panorama-actions {
  position: absolute;
  z-index: 3;
  inset-block-start: var(--gap-md);
  inset-inline-start: var(--gap-md);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--q-primary);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--surface) 92%, transparent);
  box-shadow: 0 0.25rem 0.75rem color-mix(in srgb, black 20%, transparent);
  backdrop-filter: blur(0.5rem);
}

.panorama-action {
  min-height: 2.5rem;
  padding: var(--gap-sm) var(--gap-md-lg);
  border: 0;
  border-block-start: 1px solid
    color-mix(in srgb, var(--q-primary) 35%, transparent);
  background: transparent;
  color: var(--q-primary);
  cursor: pointer;
  font: inherit;
  font-size: var(--type-sm);
  font-weight: 600;
  text-align: start;
}

.panorama-action:first-child {
  border-block-start: 0;
}

.panorama-action:hover {
  background: color-mix(in srgb, var(--q-primary) 10%, transparent);
}

.panorama-action:disabled {
  cursor: wait;
  opacity: 0.55;
}

.panorama-action:focus-visible {
  position: relative;
  outline: 0.125rem solid var(--q-primary);
  outline-offset: -0.125rem;
}
</style>
