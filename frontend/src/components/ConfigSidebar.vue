<script lang="ts" setup>
import { readAlbum, updateAlbum } from "@/client";
import { useAlbum } from "@/utils/albumStore.ts";
import { useUserLocation } from "@/utils/geocoding.ts";
import { toRangeList } from "@/utils/ranges";
import { chooseTextDir } from "@/utils/text.ts";
import { storeToRefs } from "pinia";
import { ref } from "vue";

defineProps<{
  tripNames: string[];
}>();

const userLocationStore = useUserLocation();
const useHomeLocation = ref(false);

const albumStore = useAlbum();
const { album } = storeToRefs(albumStore);

const emit = defineEmits<{
  (e: "print"): void;
}>();

const selectedTrip = ref<string | null>(null);

const onTripSelected = async ({ value: aid }: { value: string }) => {
  const { data } = await readAlbum({ path: { aid } });
  album.value = data;
};

albumStore.$subscribe((_, { album }) => {
  if (album)
    void updateAlbum({
      path: { aid: album.id },
      body: album,
    });
});

const ruleRequired = (val: string): true | string => {
  if (!val || !val.trim()) return "Step ranges are required";
  return true;
};
const ruleRangesFormat = (val: string): true | string => {
  try {
    toRangeList(val);
  } catch {
    return "Use format: 0-20 or 0-5, 10-15";
  }
  return true;
};

const toTitleCase = (str: string) =>
  str
    .replace(/([a-z])-/g, "$1 ")
    .replace(/_\d+$/, "")
    .replace(
      /\w\S*/g,
      (text) => text.charAt(0).toUpperCase() + text.substring(1).toLowerCase(),
    );
</script>

<template>
  <div class="fit column q-pa-lg q-gutter-y-md">
    <!--  Title  -->
    <div class="row items-center">
      <q-icon class="on-left" name="img:/favicon.svg" size="sm" />
      <div class="text-subtitle1 text-weight-bold">
        Polarsteps Album Generator
      </div>
    </div>

    <!--  Trip select  -->
    <q-select
      v-model="selectedTrip"
      :options="
        tripNames.map((value) => ({ label: toTitleCase(value), value }))
      "
      class="text-subtitle1"
      dense
      filled
      options-dense
      @update:model-value="onTripSelected"
    />

    <!--  Config form  -->

    <div v-if="album" class="col q-gutter-sm">
      <q-input
        v-model="album.title"
        :dir="chooseTextDir(album.title)"
        bottom-slots
        dense
        label="Title"
        outlined
      />
      <q-input
        v-model="album.subtitle"
        :dir="chooseTextDir(album.subtitle)"
        bottom-slots
        dense
        label="Subtitle"
        outlined
      />
      <q-input
        v-model="album.front_cover_photo"
        bottom-slots
        dense
        label="Front Cover Photo"
        outlined
      />
      <q-input
        v-model="album.back_cover_photo"
        bottom-slots
        dense
        label="Back Cover Photo"
        outlined
      />
      <q-input
        v-model="album.steps_ranges"
        :rules="[ruleRequired, ruleRangesFormat]"
        debounce="500"
        dense
        label="Steps to Include"
        lazy-rules
        outlined
        placeholder="e.g. 0-20, 30"
      />
      <q-input
        v-model="album.maps_ranges"
        :rules="[ruleRangesFormat]"
        debounce="500"
        dense
        label="Map Step Ranges"
        lazy-rules
        outlined
        placeholder="e.g. 0-20, 30"
      />

      <div class="row items-center justify-between">
        <div>
          <div class="text-subtitle2">Home Location</div>
          <div class="text-caption text-grey-5">
            <strong v-if="userLocationStore.location">
              {{ userLocationStore.location.name }} ({{
                userLocationStore.location.detail
              }})
            </strong>
            <div v-else>Enable to see distance from home</div>
          </div>
        </div>
        <q-toggle
          v-model="useHomeLocation"
          @update:model-value="
            (checked) =>
              checked ? userLocationStore.set() : userLocationStore.clear()
          "
        />
      </div>
    </div>

    <q-btn
      v-if="album"
      class="full-width text-h6"
      color="primary"
      icon="print"
      label="Print"
      no-caps
      push
      @click="emit('print')"
    />
  </div>
</template>
