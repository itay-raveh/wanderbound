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
  panorama.value
    ? symOutlinedFilterCenterFocus
    : symOutlinedPanoramaPhotosphere,
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
  <div class="panorama-actions album-actions" @click.stop>
    <button
      type="button"
      class="panorama-frame-action panorama-action album-action"
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
        'panorama-action album-action',
        makeFullPage ? 'panorama-full-page-action' : 'panorama-spread-action',
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
      class="panorama-disable-action panorama-action album-action"
      :disabled="disabling"
      :aria-label="t('panorama.frame.disable')"
      @click="disablePanorama"
    >
      <q-icon :name="symOutlinedPhoto" />
      <q-tooltip>{{ t("panorama.frame.disable") }}</q-tooltip>
    </button>
    <slot />
  </div>
</template>

<style lang="scss" scoped src="./AlbumActions.scss"></style>
