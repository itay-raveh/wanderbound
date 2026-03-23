import CoverPhotoPicker from "@/components/album/CoverPhotoPicker.vue";
import { mountWithPlugins } from "../helpers";

function mountPicker(props: Record<string, unknown> = {}) {
  return mountWithPlugins(CoverPhotoPicker, {
    props: {
      modelValue: "photo1.jpg",
      albumId: "album-123",
      label: "Front Cover",
      photos: ["photo1.jpg", "photo2.jpg", "photo3.jpg"],
      ...props,
    },
  });
}

describe("CoverPhotoPicker", () => {
  it("renders the label in the pill button", () => {
    const wrapper = mountPicker({ label: "Back Cover" });
    const pill = wrapper.find(".picker-pill");
    expect(pill.text()).toContain("Back Cover");
  });

  it("starts with the panel closed", () => {
    const wrapper = mountPicker();
    const panel = wrapper.find(".picker-panel");
    // v-show makes it display:none, but the element exists
    expect(panel.exists()).toBe(true);
    expect((panel.element as HTMLElement).style.display).toBe("none");
  });

  it("toggles the panel open on pill click", async () => {
    const wrapper = mountPicker();
    const pill = wrapper.find(".picker-pill");

    await pill.trigger("click");

    const panel = wrapper.find(".picker-panel");
    expect((panel.element as HTMLElement).style.display).not.toBe("none");
  });

  it("toggles the panel closed on second pill click", async () => {
    const wrapper = mountPicker();
    const pill = wrapper.find(".picker-pill");

    await pill.trigger("click");
    await pill.trigger("click");

    const panel = wrapper.find(".picker-panel");
    expect((panel.element as HTMLElement).style.display).toBe("none");
  });

  it("rotates chevron icon when open", async () => {
    const wrapper = mountPicker();
    const pill = wrapper.find(".picker-pill");

    // Initially not rotated
    let chevron = wrapper.find(".pill-chevron");
    expect(chevron.classes()).not.toContain("rotated");

    await pill.trigger("click");

    chevron = wrapper.find(".pill-chevron");
    expect(chevron.classes()).toContain("rotated");
  });

  it("renders photo grid cells for each photo", async () => {
    const wrapper = mountPicker({
      photos: ["a.jpg", "b.jpg", "c.jpg"],
    });

    await wrapper.find(".picker-pill").trigger("click");

    const cells = wrapper.findAll(".grid-cell");
    expect(cells).toHaveLength(3);
  });

  it("marks the currently selected photo with 'selected' class", async () => {
    const wrapper = mountPicker({
      modelValue: "photo2.jpg",
      photos: ["photo1.jpg", "photo2.jpg", "photo3.jpg"],
    });

    await wrapper.find(".picker-pill").trigger("click");

    const cells = wrapper.findAll(".grid-cell");
    const selectedCells = cells.filter((c) => c.classes().includes("selected"));
    expect(selectedCells).toHaveLength(1);

    // The second cell should be selected
    expect(cells[1]!.classes()).toContain("selected");
  });

  it("emits update:modelValue when a photo is clicked", async () => {
    const wrapper = mountPicker({
      modelValue: "photo1.jpg",
      photos: ["photo1.jpg", "photo2.jpg", "photo3.jpg"],
    });

    await wrapper.find(".picker-pill").trigger("click");

    const cells = wrapper.findAll(".grid-cell");
    await cells[1]!.trigger("click");

    expect(wrapper.emitted("update:modelValue")).toBeTruthy();
    expect(wrapper.emitted("update:modelValue")![0]).toEqual(["photo2.jpg"]);
  });

  it("closes the panel after selecting a photo", async () => {
    const wrapper = mountPicker({
      modelValue: "photo1.jpg",
      photos: ["photo1.jpg", "photo2.jpg"],
    });

    await wrapper.find(".picker-pill").trigger("click");

    const cells = wrapper.findAll(".grid-cell");
    await cells[1]!.trigger("click");

    const panel = wrapper.find(".picker-panel");
    expect((panel.element as HTMLElement).style.display).toBe("none");
  });

  it("shows empty message when photos array is empty", async () => {
    const wrapper = mountPicker({ photos: [] });

    await wrapper.find(".picker-pill").trigger("click");

    const empty = wrapper.find(".picker-empty");
    expect(empty.exists()).toBe(true);
    expect(empty.text()).toContain("No landscape photos");
  });

  it("renders images with correct src using mediaThumbUrl", async () => {
    const wrapper = mountPicker({
      albumId: "test-album",
      photos: ["pic.jpg"],
    });

    await wrapper.find(".picker-pill").trigger("click");

    const img = wrapper.find(".cell-img");
    expect(img.exists()).toBe(true);
    // mediaThumbUrl builds: baseUrl/api/v1/albums/{albumId}/media/{name}?w=200
    expect(img.attributes("src")).toContain("test-album");
    expect(img.attributes("src")).toContain("pic.jpg");
  });
});
