import { nextTick, ref } from "vue";
import { mountWithPlugins } from "../helpers";
import PdfExportButton from "@/components/editor/PdfExportButton.vue";
import type { PdfExportTarget } from "@/composables/usePdfExportStream";

const start = vi.fn();
const abort = vi.fn();
let targetGetter: (() => PdfExportTarget) | null = null;

vi.mock("@/composables/usePhotoQuality", () => ({
  qualitySummary: ref({ caution: 0, warning: 0 }),
}));

vi.mock("@/composables/usePdfExportStream", async () => {
  const vue = await vi.importActual<typeof import("vue")>("vue");
  return {
    usePdfExportStream: vi.fn(
      (_aid: () => string, target: () => PdfExportTarget) => {
        targetGetter = target;
        return {
          start,
          abort,
          state: vue.ref("idle"),
          progress: vue.ref({
            phase: "queued",
            done: 0,
            total: null,
            message: "",
          }),
        };
      },
    ),
  };
});

const chapters = [
  {
    id: "andes",
    title: "Andes",
    subtitle: "",
    step_ids: [1],
    front_cover_photo: "front.jpg",
    back_cover_photo: "back.jpg",
  },
  {
    id: "patagonia",
    title: "Patagonia",
    subtitle: "",
    step_ids: [2],
    front_cover_photo: "front.jpg",
    back_cover_photo: "back.jpg",
  },
];

function confirmExport() {
  Array.from(document.querySelectorAll<HTMLButtonElement>("button"))
    .find((button) => button.textContent?.includes("Export selected"))
    ?.click();
}

function mountExportButton() {
  return mountWithPlugins(PdfExportButton, {
    props: { albumId: "trip-1", chapters },
    attachTo: document.body,
  });
}

describe("PdfExportButton", () => {
  beforeEach(() => {
    start.mockReset();
    abort.mockReset();
    targetGetter = null;
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("opens chapter selection from the primary export button", async () => {
    const wrapper = mountExportButton();

    expect(wrapper.get("button").text()).toContain("Export PDF");
    expect(wrapper.text()).not.toContain("More exports");
    await wrapper.get("button").trigger("click");
    await nextTick();

    expect(document.body.textContent).toContain("Export chapters");
    expect(document.body.textContent).toContain("All chapters");
    expect(document.body.textContent).toContain("Andes");
    expect(document.body.textContent).toContain("Patagonia");
    expect(start).not.toHaveBeenCalled();
  });

  it("starts a single selected chapter as a chapter PDF export", async () => {
    const wrapper = mountExportButton();

    await wrapper.get("button").trigger("click");
    await nextTick();
    document
      .querySelectorAll<HTMLInputElement>('input[type="checkbox"]')[2]
      ?.click();
    await nextTick();
    confirmExport();

    expect(start).toHaveBeenCalledTimes(1);
    expect(targetGetter?.()).toEqual({ type: "chapter", id: "andes" });
  });

  it("starts multiple selected chapters as a chapter ZIP export", async () => {
    const wrapper = mountExportButton();

    await wrapper.get("button").trigger("click");
    await nextTick();
    confirmExport();

    expect(start).toHaveBeenCalledTimes(1);
    expect(targetGetter?.()).toEqual({
      type: "chapters",
      ids: ["andes", "patagonia"],
    });
  });
});
