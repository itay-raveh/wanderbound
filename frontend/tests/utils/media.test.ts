import {
  isVideo,
  posterPath,
  mediaSrcset,
  THUMB_WIDTHS,
} from "@/utils/media";

describe("isVideo", () => {
  it("returns true for .mp4 files", () => {
    expect(isVideo("clip.mp4")).toBe(true);
  });

  it("returns false for non-video files", () => {
    expect(isVideo("photo.jpg")).toBe(false);
    expect(isVideo("image.png")).toBe(false);
  });

  it("is case-sensitive (MP4 returns false)", () => {
    expect(isVideo("clip.MP4")).toBe(false);
  });

  it("returns false for name containing .mp4 not at the end", () => {
    expect(isVideo("clip.mp4.backup")).toBe(false);
  });
});

describe("posterPath", () => {
  it("replaces .mp4 with .jpg for video files", () => {
    expect(posterPath("clip.mp4")).toBe("clip.jpg");
  });

  it("returns the same path for non-video files", () => {
    expect(posterPath("photo.jpg")).toBe("photo.jpg");
  });
});

describe("mediaSrcset", () => {
  it("builds srcset string with all thumb widths", () => {
    const result = mediaSrcset("photo.jpg", "abc");
    const parts = result.split(", ");
    expect(parts).toHaveLength(THUMB_WIDTHS.length);
    for (const w of THUMB_WIDTHS) {
      expect(result).toContain(`?w=${w} ${w}w`);
    }
  });
});
