<script lang="ts" setup>
import type { Album, Segment, Step } from "@/client";
import { useUserLocation } from "@/utils/geocoding.ts";
import { computed } from "vue";
import { date } from "quasar";
import OverviewCountryColumn from "@/components/album/overview/OverviewCountryColumn.vue";
import OverviewStatItem from "@/components/album/overview/OverviewStatItem.vue";
import OverviewFurthestPoint from "@/components/album/overview/OverviewFurthestPoint.vue";

const props = defineProps<{
  album: Album;
  steps: Step[];
  segments: Segment[];
}>();

const userLocation = useUserLocation();

const stepsCount = computed(() => props.steps.length.toLocaleString());

const { getDateDiff } = date;

const daysCount = computed(() => {
  const start = new Date(props.steps[0]!.datetime);
  const end = new Date(props.steps[props.steps.length - 1]!.datetime);
  return getDateDiff(end, start, "days");
});

const photosCount = computed(() =>
  props.steps
    .flatMap(({ pages }) => pages.flatMap((page) => page.length))
    .reduce((a, b) => a + b, 0),
);

const countries = computed(() =>
  Object.entries(
    Object.fromEntries(
      props.steps.map(({ location }) => [
        location.country_code,
        location.detail,
      ]),
    ),
    // When the user has a step in no-mans-land.
    // Polarsteps marks that '00'.
    // Obviously we don't need that in our country list.
  ).filter(([code]) => code !== "00"),
);

const totalKm = computed(() => {
  return Math.round(
    props.segments.reduce((acc, seg) => acc + seg.length_km, 0),
  ).toLocaleString();
});
</script>

<template>
  <div class="page-container row">
    <OverviewCountryColumn :countries="countries" class="col-4" />
    <div class="col bg column items-center">
      <div
        :style="{ width: '60%' }"
        class="col-8 column justify-evenly q-pt-xl"
      >
        <div class="row justify-between">
          <OverviewStatItem
            :value="daysCount"
            class="col-5"
            icon="sym_o_calendar_month"
            unit="Days"
          />
          <OverviewStatItem
            :value="totalKm"
            class="col-5"
            icon="sym_o_explore"
            unit="Kilometers"
          />
        </div>
        <div class="row justify-between">
          <OverviewStatItem
            :value="photosCount"
            class="col-5"
            icon="sym_o_photo_camera"
            unit="Photos"
          />
          <OverviewStatItem
            :value="stepsCount"
            class="col-5"
            icon="sym_o_timeline"
            unit="Steps"
          />
        </div>
      </div>
      <div class="col fit">
        <OverviewFurthestPoint
          v-if="userLocation.location"
          :home="userLocation.location"
          :steps="steps"
        />
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.bg {
  background-size: 100%;
  background-position: 100%;
  background-repeat: no-repeat;
  background-image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjE0OSIgaGVpZ2h0PSIyNDgwIiB2aWV3Qm94PSIwIDAgMjE0OSAyNDgwIiBmaWxsPSJub25lIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPgo8ZyBvcGFjaXR5PSIwLjI0Ij4KPG1hc2sgaWQ9Im1hc2swXzI2XzIxOCIgc3R5bGU9Im1hc2stdHlwZTpsdW1pbmFuY2UiIG1hc2tVbml0cz0idXNlclNwYWNlT25Vc2UiIHg9IjAiIHk9IjAiIHdpZHRoPSIyMTQ5IiBoZWlnaHQ9IjI0ODAiPgo8cmVjdCB3aWR0aD0iMjE0OSIgaGVpZ2h0PSIyNDgwIiBmaWxsPSJ3aGl0ZSIvPgo8L21hc2s+CjxnIG1hc2s9InVybCgjbWFzazBfMjZfMjE4KSI+CjxwYXRoIGZpbGwtcnVsZT0iZXZlbm9kZCIgY2xpcC1ydWxlPSJldmVub2RkIiBkPSJNNzYuNTE1NiAxODg0LjgzQzc2LjUxNTYgMTg4NC44MyA0OTIuNzk3IDE4MjIuMzYgNzUxLjAzMSAxNjc5LjU5QzEwMDkuMjcgMTUzNi44MyAxMDYzLjI1IDE3ODEuNzUgMTI3NS44NiAxNzgxLjc1QzE0ODguNDcgMTc4MS43NSAxODcxLjQyIDE3NjguNjQgMTk2Mi45NyAxNzE1LjY0QzIwNTQuNTIgMTY2Mi42NCAyMDY2LjI1IDE2NTUuMTYgMjE0MC4xMSAxNjc3LjIyQzIyMTMuOTcgMTY5OS4yOCAyMjM1Ljk3IDIyMjIuMTcgMjIzNS45NyAyMjIyLjE3TDY2NC4yMDMgMjIzOC44OUw3Ni41MTU2IDE4ODQuODNaIiBmaWxsPSIjRTlFQUVDIi8+CjxwYXRoIGZpbGwtcnVsZT0iZXZlbm9kZCIgY2xpcC1ydWxlPSJldmVub2RkIiBkPSJNMTA1OS42OSAyMTU4LjExQzEwNTkuNjkgMjE1OC4xMSAxOTY1LjMgMTkxNy44MSAyMTY1LjUyIDE3NDQuODRDMjM2NS43MyAxNTcxLjg3IDIyMzYuNTkgMjMwNi44MSAyMjM2LjU5IDIzMDYuODFDMjIzNi41OSAyMzA2LjgxIDE2NjQuNTYgMjM2My40NCAxNjQ3LjkxIDIzNjMuNDRDMTYzMS4yNSAyMzYzLjQ0IDEwNTkuNjkgMjE1OC4xMSAxMDU5LjY5IDIxNTguMTFaIiBmaWxsPSIjQkRDMUM3Ii8+CjxwYXRoIGZpbGwtcnVsZT0iZXZlbm9kZCIgY2xpcC1ydWxlPSJldmVub2RkIiBkPSJNMi4yODEyNSAxODYxLjU5QzIuMjgxMjUgMTg2MS41OSAzMTYuMzQ0IDE5MTAuMTcgNDIyLjQyMiAxOTk4LjE0QzUyOC41IDIwODYuMTEgNTAxLjcwMyAyMDc1LjUyIDU4My4wNDcgMjA3NS41MkM2NjQuMzkxIDIwNzUuNTIgNjEwLjkyMiAyMTc4LjgxIDgxOS40MjIgMjE0OC4yNUMxMDI3LjkyIDIxMTcuNjkgOTYzLjAxNiAyMTc4Ljk3IDEwNjYuODYgMjEzOS4xMkMxMTcwLjcgMjA5OS4yOCAxMTkxLjEyIDIxNzIuNTkgMTI3Ny40NSAyMTcyLjU5QzEzNjMuNzggMjE3Mi41OSAxNTQzLjQxIDIxNzkuNDcgMTYwNi44NCAyMjE3Ljc4QzE2NzAuMjggMjI1Ni4wOSAxNzg0LjM5IDIyMzIuMTkgMTg2NC4zOCAyMjgxLjI1QzE5NDQuMzYgMjMzMC4zMSAyMDE5LjA4IDIxODcuNjYgMjExOS41OCAyMTgwLjEyQzIyMjAuMDggMjE3Mi41OSAyMjk3LjE2IDIyMDguMiAyMjk3LjE2IDIyMDguMkwyMjcxLjkxIDI1MjkuODhMLTI3LjQ1MzEgMjQ5OC42NkwyLjI4MTI1IDE4NjEuNTlaIiBmaWxsPSIjOTE5OEExIi8+CjxwYXRoIGZpbGwtcnVsZT0iZXZlbm9kZCIgY2xpcC1ydWxlPSJldmVub2RkIiBkPSJNLTEwLjcwMzMgMjEwOS42MUMtMTAuNzAzMyAyMTA5LjYxIDE3Ni4wNjIgMjE0Ny44NCAyNzEuMDMxIDIxOTUuNDJDMzY2IDIyNDMgNDg5Ljg1OSAyMjY3LjQ4IDUzMi4yNSAyMjY3LjQ4QzU3NC42NDEgMjI2Ny40OCA2MTkuNzUgMjIyNS45MSA2NzQuOTA2IDIyMjUuOTFDNzMwLjA2MiAyMjI1LjkxIDc5MC4xNzIgMjIxNC4yNyA4NTUgMjI1MS43OEM5MTkuODI4IDIyODkuMyAxMDg5LjUgMjI1My42OSAxMjM0LjY0IDIzMTQuOThDMTM3OS43OCAyMzc2LjI4IDE0NTMuNzggMjM5NS4yMiAxNTA1Ljk1IDIzOTUuMjJDMTU1OC4xMiAyMzk1LjIyIDE2NzcuMzMgMjQ5Mi45OCAxNjc3LjMzIDI0OTIuOThILTIxLjMyMzJMLTEwLjcwMzMgMjEwOS42MVoiIGZpbGw9IiM1NDVCNjMiLz4KPC9nPgo8L2c+Cjwvc3ZnPg==);
}
</style>
