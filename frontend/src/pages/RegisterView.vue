<script lang="ts" setup>
import { useQuasar } from "quasar";
import { ref } from "vue";
import { useRouter } from "vue-router";

const router = useRouter();
const $q = useQuasar();

const showHelp = ref(false);

async function onUploaded() {
  await router.push("/");
}

function onFailed(info: { xhr: XMLHttpRequest }) {
  const status = info.xhr?.status;
  $q.notify({
    type: "negative",
    message: `Upload failed. ${status ? `Server returned ${status}.` : "Please try again"}`,
  });
}
</script>

<template>
  <q-page
    class="window-height window-width row items-center justify-center p-4 relative-position"
    style="background: linear-gradient(to bottom right, #0f0f1a, #000000)"
  >
    <div class="col-12 col-md-8 col-lg-6 flex column items-center">
      <!-- Hero Section -->
      <div class="column items-center text-center q-mb-xl">
        <div class="row items-center justify-center q-mb-md">
          <q-img
            class="q-mr-md"
            src="/icon.svg"
            style="width: 96px; height: 96px"
          />
          <div class="text-h3 text-weight-bold tracking-tight text-primary">
            Polarsteps Album Generator
          </div>
        </div>
        <div class="text-h6 text-grey-5 text-weight-medium">
          Turn your adventures into beautiful, printable albums.
        </div>
      </div>

      <!-- Upload Card -->
      <q-card
        class="w-full q-pa-xl bg-card border-card flex column items-center backdrop-filter"
        style="
          max-width: 800px;
          background: rgba(37, 37, 64, 0.8);
          border: 1px solid var(--border-color);
        "
      >
        <div class="row items-center justify-center q-mb-lg full-width">
          <div class="text-h5 text-center q-mr-sm">
            Upload your <strong>user_data.zip</strong> to begin
          </div>
          <q-btn
            color="grey-5"
            dense
            flat
            icon="help_outline"
            round
            @click="showHelp = true"
          />
        </div>

        <q-uploader
          accept=".zip"
          auto-upload
          class="w-full custom-upload"
          field-name="file"
          flat
          label="Drop .zip file here"
          style="width: 100%; max-width: 600px; height: 200px"
          url="/api/v1/upload"
          with-credentials
          @failed="onFailed"
          @uploaded="onUploaded"
        />
      </q-card>
    </div>

    <!-- Help Dialog -->
    <q-dialog v-model="showHelp" backdrop-filter="blur(6px)">
      <q-card class="q-pa-lg" style="max-width: 600px">
        <div class="text-h6 q-mb-md">
          Download a copy of your Polarsteps data:
        </div>
        <ul>
          <li class="q-mb-sm">
            Log in at
            <a
              class="text-primary"
              href="https://www.polarsteps.com"
              target="_blank"
              >Polarsteps</a
            >
            using a laptop or desktop computer.
          </li>
          <li class="q-mb-sm">
            Click on your name on the top right of the page and select
            <strong>Account settings</strong>.
          </li>
          <li class="q-mb-sm">
            Scroll down to <strong>Download my data</strong> in the privacy
            section.
          </li>
          <li class="q-mb-sm">
            Click the blue link to
            <strong>Download a copy of your data</strong>.
          </li>
          <li class="q-mb-sm">Click <strong>Start My Archive</strong>.</li>
          <li class="q-mb-sm">
            You will receive an email with a link to download a file with your
            data.
          </li>
        </ul>
        <div class="row justify-end q-mt-md">
          <q-btn v-close-popup color="primary" flat label="Close" />
        </div>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<style scoped>
.custom-upload {
  border: 2px dashed var(--border-color);
  background: transparent;
  transition: all 0.2s ease;
}

.custom-upload:hover {
  border-color: var(--q-primary);
  background: rgba(74, 158, 255, 0.05);
}
</style>
