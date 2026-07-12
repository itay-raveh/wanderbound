import { invalidateAlbumKey, queryKeys } from "@/queries/keys";

describe("invalidateAlbumKey", () => {
  it("invalidates print bundle families non-exactly", () => {
    expect(invalidateAlbumKey(queryKeys.printBundles("album-1"))).toEqual({
      key: queryKeys.printBundles("album-1"),
      exact: false,
    });
  });

  it("invalidates ordinary album keys exactly", () => {
    expect(invalidateAlbumKey(queryKeys.media("album-1"))).toEqual({
      key: queryKeys.media("album-1"),
      exact: true,
    });
  });
});
