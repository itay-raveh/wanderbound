<script lang="ts" setup>
import { getAlbumNames } from "@/api";
import ConfigSidebar from "@/components/ConfigSidebar.vue";
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useAlbum } from "@/utils/albumStore.ts";
import { storeToRefs } from "pinia";
import AlbumViewer from "@/components/AlbumViewer.vue";
import { useQuasar } from "quasar";

const router = useRouter();
const $q = useQuasar();

const albumStore = useAlbum();
const { album } = storeToRefs(albumStore);

const albumNames = ref<string[]>();

onMounted(async () => {
  try {
    const { data } = await getAlbumNames({});
    albumNames.value = data;
  } catch {
    await router.push("/register");
  }
});

const handlePrint = async () => {
  console.log("Print: start");

  $q.loading.show({
    delay: 400,
  });

  document.querySelectorAll("img").forEach((img: HTMLImageElement) => {
    console.log("Loading image: " + img.src);
    img.loading = "eager";
  });

  await new Promise((r) => setTimeout(r, 2000));
  $q.loading.hide();
  await new Promise((r) => setTimeout(r, 500));

  console.log("Print: end");

  window.print();
};
</script>

<template>
  <q-page class="row q-pa-md q-gutter-x-md" padding>
    <div class="col-3 section print-hide">
      <ConfigSidebar
        v-if="albumNames"
        :tripNames="albumNames"
        @print="handlePrint"
      />
    </div>

    <div class="col section">
      <AlbumViewer v-if="album" :album="album" />
    </div>
  </q-page>
</template>

<style lang="scss" scoped>
@media not print {
  .section {
    background: #1f2a47;
    border-radius: 12px;
  }
}

@media print {
  @page {
    size: A4 landscape;
  }

  * {
    margin: 0;
    padding: 0;
    print-color-adjust: exact;
    -webkit-print-color-adjust: exact;
  }
}
</style>
