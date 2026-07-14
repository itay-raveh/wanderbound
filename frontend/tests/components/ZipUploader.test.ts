import { mountWithPlugins } from "../helpers";
import ZipUploader from "@/components/register/ZipUploader.vue";
import { nextTick } from "vue";

const upload = vi.hoisted(() => ({
  addFile: vi.fn(),
  cancel: vi.fn(),
  reset: vi.fn(),
  state: undefined as
    | undefined
    | {
        file: { value: File | null };
        status: { value: "idle" | "uploading" | "processing" | "failed" };
        progress: { value: number };
        processingPhase: {
          value: "downloading" | "validating" | "importing" | null;
        };
        errorCode: { value: string | null };
      },
}));

vi.mock("@/composables/useDirectZipUpload", async () => {
  const { ref } = await import("vue");
  return {
    useDirectZipUpload: () => {
      upload.state = {
        file: ref<File | null>(null),
        status: ref("idle"),
        progress: ref(0),
        processingPhase: ref(null),
        errorCode: ref<string | null>(null),
      };
      return { ...upload.state, ...upload };
    },
  };
});

describe("ZipUploader", () => {
  beforeEach(() => vi.clearAllMocks());

  it("keeps the file picker keyboard accessible", async () => {
    const wrapper = mountWithPlugins(ZipUploader);
    const dropZone = wrapper.get('[role="button"]');
    const selected = new File(["zip"], "polarsteps.zip", {
      type: "application/zip",
    });

    expect(dropZone.attributes("tabindex")).toBe("0");
    Object.defineProperty(wrapper.get('input[type="file"]').element, "files", {
      value: [selected],
    });
    await wrapper.get('input[type="file"]').trigger("change");

    expect(upload.addFile).toHaveBeenCalledWith(selected);
  });

  it("shows transfer progress and allows cancellation", async () => {
    const wrapper = mountWithPlugins(ZipUploader);
    upload.state!.file.value = new File(["zip"], "polarsteps.zip");
    upload.state!.status.value = "uploading";
    upload.state!.progress.value = 0.42;
    await nextTick();

    expect(wrapper.get('[role="progressbar"]').attributes("aria-valuenow")).toBe(
      "0.42",
    );
    await wrapper.get("button").trigger("click");
    expect(upload.cancel).toHaveBeenCalledOnce();
  });

  it("shows one retry action for an application failure", async () => {
    const wrapper = mountWithPlugins(ZipUploader);
    upload.state!.status.value = "failed";
    upload.state!.errorCode.value = "upload_invalid_zip";
    await nextTick();

    expect(wrapper.text()).toContain("not a valid Polarsteps export");
    await wrapper.get("button").trigger("click");
    expect(upload.reset).toHaveBeenCalledOnce();
  });

  it("shows the current ingestion phase", async () => {
    const wrapper = mountWithPlugins(ZipUploader);
    upload.state!.file.value = new File(["zip"], "polarsteps.zip");
    upload.state!.status.value = "processing";
    upload.state!.processingPhase.value = "importing";
    await nextTick();

    expect(wrapper.text()).toContain("Importing your trips and photos");
  });
});
