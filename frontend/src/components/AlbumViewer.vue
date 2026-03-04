<script lang="ts" setup>
import { type Album, getSegments, getStepRanges } from "@/api";
import MapPage from "./album/MapPage.vue";
import OverviewPage from "./album/overview/OverviewPage.vue";
import Step from "./album/Step.vue";
import CoverPage from "./album/CoverPage.vue";
import { toRangeList } from "@/utils/ranges.ts";
import { computedAsync } from "@vueuse/core";

const props = defineProps<{
  album: Album;
}>();

const steps = computedAsync(async () => {
  const { data: steps } = await getStepRanges({
    path: { aid: props.album.id },
    body: toRangeList(props.album.steps_ranges),
  });
  console.log(steps);
  return steps;
}, null);

const segments = computedAsync(async () => {
  if (!steps.value) return null;
  const { data: segments } = await getSegments({
    path: { aid: props.album.id },
    query: {
      first: steps.value[0]!.idx,
      last: steps.value[steps.value.length - 1]!.idx,
    },
  });
  console.log(segments);
  return segments;
}, null);
</script>

<template>
  <div v-if="steps && segments" class="album-container scroll-y fit">
    <CoverPage :album="album" :steps="steps" />
    <CoverPage :album="album" :steps="steps" is-back />
    <OverviewPage :album="album" :segments="segments" :steps="steps" />
    <MapPage :segments="segments" :steps="steps" />
    <template v-for="step in steps" :key="step.id">
      <Step :album="album" :step="step" />
    </template>
  </div>
  <div v-else class="fit relative-position">
    <q-inner-loading
      :label="`Loading '${album.title || album.id}'...`"
      showing
    />
  </div>
</template>

<style lang="scss" scoped>
.page-container {
  width: 297mm;
  height: 210mm;
  background-color: var(--q-dark);
}

@media not print {
  .album-container {
    contain: strict;
  }

  .page-container {
    scale: 0.8;
    padding: 5mm;
    border: 1px dashed white;
  }
}

@media print {
  .album-container {
    padding: 0;
  }

  .page-container {
    break-after: always;
    break-inside: avoid;
    margin: 0;
  }
}
</style>
