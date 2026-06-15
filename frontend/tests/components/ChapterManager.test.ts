import { describe, expect, test, vi, beforeEach } from "vitest";
import ChapterManager from "@/components/editor/ChapterManager.vue";
import { mountWithPlugins, makeStep } from "../helpers";
import { mockAlbum, mockMedia } from "../fixtures/mocks";
import type { AlbumChapter } from "@/client";

const mutate = vi.fn();

vi.mock("@/queries/useAlbumMutation", () => ({
  useAlbumMutation: () => ({ mutate }),
}));

beforeEach(() => {
  mutate.mockReset();
});

describe("ChapterManager", () => {
  test("shows unassigned steps and creates a chapter from them", async () => {
    const steps = [
      makeStep({ id: 1, name: "Buenos Aires" }),
      makeStep({ id: 2, name: "Ushuaia" }),
    ];
    const wrapper = mountWithPlugins(ChapterManager, {
      props: {
        album: { ...mockAlbum, chapters: [] },
        steps,
        media: mockMedia,
      },
    });

    expect(wrapper.text()).toContain("Buenos Aires");
    expect(wrapper.text()).toContain("Ushuaia");

    await wrapper.get(".add-chapter").trigger("click");

    expect(mutate).toHaveBeenCalledWith({
      chapters: [
        expect.objectContaining({
          id: expect.stringMatching(/^chapter-/),
          step_ids: [1, 2],
        }),
      ],
    });
  });

  test("does not create an empty chapter when every step is assigned", async () => {
    const steps = [makeStep({ id: 1, name: "Buenos Aires" })];
    const chapters: AlbumChapter[] = [
      {
        id: "chapter-1",
        title: null,
        subtitle: null,
        step_ids: [1],
        front_cover_photo: "cover.jpg",
        back_cover_photo: "cover.jpg",
      },
    ];
    const wrapper = mountWithPlugins(ChapterManager, {
      props: {
        album: { ...mockAlbum, chapters },
        steps,
        media: mockMedia,
      },
    });

    await wrapper.get(".add-chapter").trigger("click");

    expect(mutate).not.toHaveBeenCalled();
  });

  test("disables steps already assigned to another chapter", () => {
    const steps = [
      makeStep({ id: 1, name: "Buenos Aires" }),
      makeStep({ id: 2, name: "Ushuaia" }),
    ];
    const chapters: AlbumChapter[] = [
      {
        id: "chapter-1",
        title: null,
        subtitle: null,
        step_ids: [1],
        front_cover_photo: "cover.jpg",
        back_cover_photo: "cover.jpg",
      },
      {
        id: "chapter-2",
        title: null,
        subtitle: null,
        step_ids: [2],
        front_cover_photo: "cover.jpg",
        back_cover_photo: "cover.jpg",
      },
    ];
    const wrapper = mountWithPlugins(ChapterManager, {
      props: {
        album: { ...mockAlbum, chapters },
        steps,
        media: mockMedia,
      },
    });

    const stepSelect = wrapper
      .findAllComponents({ name: "QSelect" })
      .find((select) => select.props("label") === "Steps");

    expect(stepSelect?.props("options")).toEqual([
      { label: "Buenos Aires", value: 1, disable: false },
      { label: "Ushuaia", value: 2, disable: true },
    ]);
  });
});
