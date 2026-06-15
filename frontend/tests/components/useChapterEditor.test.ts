import { describe, expect, test, vi, beforeEach } from "vitest";
import { useChapterEditor } from "@/components/editor/useChapterEditor";
import { makeStep } from "../helpers";
import { mockAlbum, mockMedia } from "../fixtures/mocks";
import type { AlbumChapter } from "@/client";

const mutate = vi.fn();

vi.mock("@/queries/useAlbumMutation", () => ({
  useAlbumMutation: () => ({ mutate }),
}));

beforeEach(() => {
  mutate.mockReset();
});

describe("useChapterEditor", () => {
  test("creates a chapter from currently unassigned steps", () => {
    const editor = useChapterEditor({
      album: { ...mockAlbum, chapters: [] },
      steps: [
        makeStep({ id: 1, name: "Buenos Aires" }),
        makeStep({ id: 2, name: "Ushuaia" }),
      ],
      media: mockMedia,
    });

    editor.addChapter();

    expect(mutate).toHaveBeenCalledWith({
      chapters: [
        expect.objectContaining({
          id: "chapter-1",
          step_ids: [1, 2],
        }),
      ],
    });
  });

  test("applies a selected step range without stealing other chapter steps", () => {
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
        step_ids: [4],
        front_cover_photo: "cover.jpg",
        back_cover_photo: "cover.jpg",
      },
    ];
    const editor = useChapterEditor({
      album: { ...mockAlbum, chapters },
      steps: [
        makeStep({ id: 1, name: "One" }),
        makeStep({ id: 2, name: "Two" }),
        makeStep({ id: 3, name: "Three" }),
        makeStep({ id: 4, name: "Four" }),
      ],
      media: mockMedia,
    });

    editor.rangeDraft(chapters[0]).from = 1;
    editor.rangeDraft(chapters[0]).to = 4;
    editor.applyRange(0, chapters[0]);

    expect(mutate).toHaveBeenCalledWith({
      chapters: [{ ...chapters[0], step_ids: [1, 2, 3] }, chapters[1]],
    });
  });
});
