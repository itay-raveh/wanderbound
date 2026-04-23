import { createMatchAccumulator } from "@/composables/matchAccumulator";
import type { MatchResult } from "@/client";

const m = (
  local_name: string,
  google_id: string,
  distance: number,
  upgraded = false,
): MatchResult => ({ local_name, google_id, distance, upgraded });

describe("createMatchAccumulator", () => {
  it("merges disjoint rounds and accumulates running totals", () => {
    const acc = createMatchAccumulator();

    acc.merge({ matches: [m("a.jpg", "g1", 2, true)], totalPicked: 3 });
    acc.merge({ matches: [m("b.jpg", "g2", 5)], totalPicked: 2 });

    const summary = acc.summary(1);
    expect(summary.matched).toBe(2);
    expect(summary.totalPicked).toBe(5);
    expect(summary.alreadyUpgraded).toBe(1);
    expect(summary.unmatched).toBe(3);
    expect(summary.newThisRound).toBe(1);
  });

  it("keeps the closer match when the same local_name arrives in a later round", () => {
    const acc = createMatchAccumulator();

    acc.merge({ matches: [m("a.jpg", "far", 10)], totalPicked: 1 });
    const newlyMatched = acc.merge({
      matches: [m("a.jpg", "near", 2)],
      totalPicked: 1,
    });

    expect(newlyMatched).toBe(0);
    const [kept] = acc.summary(0).matches;
    expect(kept.google_id).toBe("near");
    expect(kept.distance).toBe(2);
  });

  it("does not double-count alreadyUpgraded when the same match arrives in a later round", () => {
    const acc = createMatchAccumulator();
    acc.merge({ matches: [m("a.jpg", "g1", 2, true)], totalPicked: 1 });
    acc.merge({ matches: [m("a.jpg", "g1", 2, true)], totalPicked: 1 });

    const summary = acc.summary(0);
    expect(summary.matched).toBe(1);
    expect(summary.alreadyUpgraded).toBe(1);
  });

  it("reset clears matches and running totals", () => {
    const acc = createMatchAccumulator();
    acc.merge({ matches: [m("a.jpg", "g1", 2, true)], totalPicked: 4 });
    acc.reset();

    const summary = acc.summary(0);
    expect(summary.matches).toEqual([]);
    expect(summary.totalPicked).toBe(0);
    expect(summary.alreadyUpgraded).toBe(0);
    expect(summary.unmatched).toBe(0);
  });
});
