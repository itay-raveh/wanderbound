<script lang="ts" setup>
import { computed } from "vue";
import { useAlbum } from "@/composables/useAlbum";
import { t } from "@/i18n";
import { useDisablePanoramaMutation } from "@/queries/usePanoramaMutation";
import {
  symOutlinedCropLandscape,
  symOutlinedFilterCenterFocus,
  symOutlinedPanoramaPhotosphere,
  symOutlinedPhoto,
  symOutlinedViewWeek,
} from "@quasar/extras/material-symbols-outlined";

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
const frameLabel = computed(() =>
  panorama.value ? t("panorama.frame.title") : t("panorama.treat"),
);
const frameIcon = computed(() =>
  panorama.value ? symOutlinedFilterCenterFocus : symOutlinedPanoramaPhotosphere,
);
const layoutLabel = computed(() =>
  props.makeFullPage ? t("panorama.makeFullPage") : t("panorama.makeSpread"),
);
const layoutIcon = computed(() =>
  props.makeFullPage ? symOutlinedCropLandscape : symOutlinedViewWeek,
);

function switchLayout(): void {
  if (props.makeFullPage) emit("make-full-page", props.media);
  else emit("make-panorama-spread", props.media);
}

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
      :aria-label="frameLabel"
      @click="emit('frame')"
    >
      <q-icon :name="frameIcon" />
      <q-tooltip>{{ frameLabel }}</q-tooltip>
    </button>
    <button
      v-if="panorama && (makeFullPage || makePanoramaSpread)"
      type="button"
      :class="[
        'panorama-action',
        makeFullPage
          ? 'panorama-full-page-action'
          : 'panorama-spread-action',
      ]"
      :aria-label="layoutLabel"
      @click="switchLayout"
    >
      <q-icon :name="layoutIcon" />
      <q-tooltip>{{ layoutLabel }}</q-tooltip>
    </button>
    <button
      v-if="panorama"
      type="button"
      class="panorama-disable-action panorama-action"
      :disabled="disabling"
      :aria-label="t('panorama.frame.disable')"
      @click="disablePanorama"
    >
      <q-icon :name="symOutlinedPhoto" />
      <q-tooltip>{{ t("panorama.frame.disable") }}</q-tooltip>
    </button>
  </div>
</template>

<style lang="scss" scoped>
.panorama-actions {
  position: absolute;
  z-index: 51;
  inset-block-start: var(--gap-md);
  inset-inline-start: var(--gap-md);
  display: flex;
  flex-direction: row;
  overflow: hidden;
  border: 1px solid var(--q-primary);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--surface) 92%, transparent);
  box-shadow: 0 0.25rem 0.75rem color-mix(in srgb, black 20%, transparent);
  backdrop-filter: blur(0.5rem);
}

.panorama-action {
  display: grid;
  width: 2.5rem;
  height: 2.5rem;
  place-items: center;
  padding: 0;
  border: 0;
  border-inline-start: 1px solid
    color-mix(in srgb, var(--q-primary) 35%, transparent);
  background: transparent;
  color: var(--q-primary);
  cursor: pointer;
  font: inherit;
  font-size: var(--type-lg);
}

.panorama-action:first-child {
  border-inline-start: 0;
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
