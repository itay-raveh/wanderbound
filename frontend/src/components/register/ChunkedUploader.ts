import { computed, ref, shallowRef } from "vue";
import { createUploaderComponent } from "quasar";

const CHUNK_SIZE = 50 * 1024 * 1024; // 50 MB

// noinspection JSUnusedGlobalSymbols
export default createUploaderComponent({
  name: "ChunkedUploader",

  props: {
    url: { type: String, required: true },
  },

  emits: ["uploaded", "failed"],

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  injectPlugin({ props, emit, helpers }: any) {
    const controllers = shallowRef<AbortController[]>([]);
    const working = ref(0);

    const isUploading = computed(() => working.value > 0);

    function abort() {
      controllers.value.forEach((c: AbortController) => c.abort());
      controllers.value = [];
    }

    async function upload() {
      const queue = helpers.queuedFiles.value.slice();
      helpers.queuedFiles.value = [];
      if (!queue.length) return;

      for (const file of queue) {
        working.value++;
        helpers.updateFileStatus(file, "uploading", 0);

        const ctrl = new AbortController();
        controllers.value.push(ctrl);
        file.__abort = () => ctrl.abort();

        const uploadId = crypto.randomUUID();
        const total = file.size;
        let offset = 0;

        try {
          while (offset < total) {
            const end = Math.min(offset + CHUNK_SIZE, total);

            const res = await fetch(`${props.url}/upload/${uploadId}`, {
              method: "PUT",
              credentials: "include",
              headers: {
                "Content-Range": `bytes ${offset}-${end - 1}/${total}`,
                "Content-Type": "application/octet-stream",
              },
              body: file.slice(offset, end),
              signal: ctrl.signal,
            });

            if (!res.ok && res.status !== 202) {
              throw new Error(`Server returned ${res.status}`);
            }

            helpers.uploadedSize.value += end - offset;
            offset = end;
            helpers.updateFileStatus(file, "uploading", offset);

            // Final chunk — server returns UserCreated
            if (offset >= total) {
              const data = await res.json();
              helpers.uploadedFiles.value =
                helpers.uploadedFiles.value.concat([file]);
              helpers.updateFileStatus(file, "uploaded");
              emit("uploaded", { files: [file], data });
            }
          }
        } catch (err) {
          if ((err as Error).name !== "AbortError") {
            helpers.uploadedSize.value -= offset;
            helpers.queuedFiles.value =
              helpers.queuedFiles.value.concat([file]);
            helpers.updateFileStatus(file, "failed");
            emit("failed", { files: [file] });
          }
        } finally {
          controllers.value = controllers.value.filter(
            (c: AbortController) => c !== ctrl,
          );
          working.value--;
        }
      }
    }

    return { isUploading, isBusy: isUploading, abort, upload: () => void upload() };
  },
});
