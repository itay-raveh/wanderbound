<script lang="ts" setup>
import OverviewLocationCircle from "@/components/album/overview/OverviewLocationCircle.vue";
import { type Location, type Step } from "@/client";
import { distance } from "@/utils/geocoding.ts";
import { computed } from "vue";

const props = defineProps<{
  home: Location;
  steps: Step[];
}>();

const furthest = computed(() => {
  let maxDist = -1;
  let loc: Location;

  for (const { location } of props.steps) {
    const dist = distance(props.home, location);

    if (dist > maxDist) {
      maxDist = dist;
      loc = location;
    }
  }

  return {
    location: loc!,
    distKm: Math.round(maxDist).toLocaleString(),
  };
});
</script>

<template>
  <div class="row fit q-pa-xl justify-between items-end arrow-bg">
    <OverviewLocationCircle
      :location="home"
      class="items-start col-4"
      icon="sym_o_home"
    />
    <div class="col relative-position full-height">
      <div
        class="absolute-center full-width text-center text-uppercase text-grey-6"
      >
        Furthest point from home
      </div>
      <div :style="{ top: '-10%' }" class="absolute bg-dark rounded-borders">
        <div class="text-h6 text-weight-bold q-mx-sm q-mb-xs">
          <span> {{ furthest.distKm }}</span>
          <span class="text-super text-grey-5">KM</span>
        </div>
        <div class="bottom-arrow"></div>
      </div>
    </div>
    <OverviewLocationCircle
      :location="furthest.location"
      class="items-end col-4"
      icon="sym_o_place"
    />
  </div>
</template>

<style lang="scss" scoped>
.arrow-bg {
  background-size: 75%;
  background-position: center 0;
  background-repeat: no-repeat;
  background-image: url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMDAwIiBoZWlnaHQ9IjMwMCIgdmlld0JveD0iMCAwIDEwMDAgMzAwIiBmaWxsPSIjOTlhIiBzdHJva2U9IiM5OWEiPjxkZWZzPjxtYXJrZXIgaWQ9ImEiIG1hcmtlcldpZHRoPSIxMCIgbWFya2VySGVpZ2h0PSIxMCIgcmVmWD0iNSIgcmVmWT0iNSI+PGNpcmNsZSBjeD0iNSIgY3k9IjUiIHI9IjEiLz48L21hcmtlcj48bWFya2VyIGlkPSJiIiBtYXJrZXJXaWR0aD0iMTAiIG1hcmtlckhlaWdodD0iMTAiIHJlZlg9IjEuNSIgcmVmWT0iMS41IiBvcmllbnQ9ImF1dG8iPjxwYXRoIGQ9Im0tMSAwIDQgMS41TDAgM3oiLz48L21hcmtlcj48L2RlZnM+PHBhdGggZD0iTTUwIDI1MHE0NTAtMjAwIDkwMCAwIiBzdHJva2Utd2lkdGg9IjUiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgZmlsbD0ibm9uZSIgbWFya2VyLXN0YXJ0PSJ1cmwoI2EpIiBtYXJrZXItZW5kPSJ1cmwoI2IpIi8+PC9zdmc+);
}

.text-super {
  font-size: 0.5em;
  margin-left: 0.5em;
  vertical-align: super;
}

.bottom-arrow {
  width: 0;
  border-left: 5px solid transparent;
  border-right: 5px solid transparent;
  border-top: 5px solid var(--q-dark);
  position: absolute;
  left: 50%;
}
</style>
