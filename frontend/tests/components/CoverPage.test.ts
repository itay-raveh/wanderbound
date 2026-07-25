import { defineComponent, h } from "vue";
import CoverPage from "@/components/album/CoverPage.vue";
import { makeAlbumMedia, makeStep, mountWithPlugins, provideTestAlbum } from "../helpers";
import { mockAlbum } from "../fixtures/mocks";

const mutate = vi.fn();

vi.mock("@/queries/useAlbumMutation", () => ({
  useAlbumMutation: () => ({ mutate }),
}));

vi.mock("@/queries/useUserQuery", () => ({
  useUserQuery: () => ({
    formatDateRange: () => "January 1, 2024",
  }),
}));

function mountCoverPage(isBack = false) {
  const chapter = {
    id: "chapter-2",
    title: "",
    subtitle: "",
    step_ids: [1],
    front_cover_photo: "cover.jpg",
    back_cover_photo: "cover.jpg",
    front_cover_darkness: 0.2,
  };
  const album = { ...mockAlbum, chapters: [mockAlbum.chapters[0], chapter] };
  const Wrapper = defineComponent({
    setup() {
      provideTestAlbum({
        media: [makeAlbumMedia({ name: "cover.jpg" })],
      });
      return () =>
        h(CoverPage, {
          album,
          chapter,
          steps: [makeStep({ id: 1, datetime: "2024-01-01T00:00:00Z" })],
          isBack,
        });
    },
  });

  return mountWithPlugins(Wrapper, {
    global: {
      stubs: {
        MediaItem: {
          props: ["media", "focusable"],
          template:
            '<div class="media-item-stub" :data-media="media" :data-focusable="String(focusable)" />',
        },
      },
    },
  });
}

describe("CoverPage", () => {
  beforeEach(() => {
    mutate.mockReset();
  });

  test("keeps empty cover text editable while preserving cover media selection", () => {
    const wrapper = mountCoverPage();

    expect(
      wrapper.get(".media-item-stub").attributes("data-focusable"),
    ).not.toBe("false");
    expect(wrapper.get(".front-title").attributes("data-placeholder")).toBe(
      "Chapter title",
    );
    expect(wrapper.get(".front-subtitle").attributes("data-placeholder")).toBe(
      "Chapter subtitle",
    );
  });

  test("dims only the front cover with the chapter darkness", () => {
    const front = mountCoverPage();
    const frontMedia = front.get(".media-item-stub");

    expect(frontMedia.classes()).toContain("cover-dimmed");
    expect(frontMedia.attributes("style")).toContain("--cover-darkness: 0.2");

    const backMedia = mountCoverPage(true).get(".media-item-stub");
    expect(backMedia.classes()).not.toContain("cover-dimmed");
    expect(backMedia.attributes("style")).toBeUndefined();
  });
});
