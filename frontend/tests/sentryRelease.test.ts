import { describe, expect, it } from "vitest";

import { sentryRelease } from "@/sentryRelease";

describe("sentryRelease", () => {
  it.each([
    ["v1.7.0", "wanderbound@1.7.0"],
    ["1.7.0", "wanderbound@1.7.0"],
    ["v1.7.0-5-g5bd3780e", "wanderbound@1.7.0-5-g5bd3780e"],
  ])("maps %s to %s", (version, expected) => {
    expect(sentryRelease(version)).toBe(expected);
  });

  it("preserves an absent development version", () => {
    expect(sentryRelease(undefined)).toBeUndefined();
  });
});
