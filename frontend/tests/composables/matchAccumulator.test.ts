import { createMatchAccumulator } from "@/composables/matchAccumulator";
import type { MatchResult } from "@/client";

const m = (local_name: string, google_id: string, distance: number): MatchResult => ({
  local_name,
  google_id,
  distance,
});

describe("createMatchAccumulator", () => {
  it("merges disjoint rounds and accumulates running totals", () => {
    const acc = createMatchAccumulator();

    acc.merge({ matches: [m("a.jpg", "g1", 2)], totalPicked: 3, alreadyUpgraded: 1 });
    acc.merge({ matches: [m("b.jpg", "g2", 5)], totalPicked: 2, alreadyUpgraded: 0 });

    const summary = acc.summary(1);
    expect(summary.matched).toBe(2);
    expect(summary.totalPicked).toBe(5);
    expect(summary.alreadyUpgraded).toBe(1);
    expect(summary.unmatched).toBe(3);
    expect(summary.newThisRound).toBe(1);
  });

  it("keeps the closer match when the same local_name arrives in a later round", () => {
    const acc = createMatchAccumulator();

    acc.merge({ matches: [m("a.jpg", "far", 10)], totalPicked: 1, alreadyUpgraded: 0 });
    const newlyMatched = acc.merge({
      matches: [m("a.jpg", "near", 2)],
      totalPicked: 1,
      alreadyUpgraded: 0,
    });

    expect(newlyMatched).toBe(0);
    const [kept] = acc.summary(0).matches;
    expect(kept.google_id).toBe("near");
    expect(kept.distance).toBe(2);
  });

  it("keeps the existing match when the later round has a larger distance", () => {
    const acc = createMatchAccumulator();
    acc.merge({ matches: [m("a.jpg", "near", 2)], totalPicked: 1, alreadyUpgraded: 0 });
    acc.merge({ matches: [m("a.jpg", "far", 10)], totalPicked: 1, alreadyUpgraded: 0 });

    const [kept] = acc.summary(0).matches;
    expect(kept.google_id).toBe("near");
  });

  it("returns the count of genuinely new local_names from merge", () => {
    const acc = createMatchAccumulator();
    acc.merge({ matches: [m("a.jpg", "g1", 2)], totalPicked: 1, alreadyUpgraded: 0 });
    const added = acc.merge({
      matches: [m("a.jpg", "g1b", 1), m("b.jpg", "g2", 3)],
      totalPicked: 2,
      alreadyUpgraded: 0,
    });
    expect(added).toBe(1);
  });

  it("reset clears matches and running totals", () => {
    const acc = createMatchAccumulator();
    acc.merge({ matches: [m("a.jpg", "g1", 2)], totalPicked: 4, alreadyUpgraded: 2 });
    acc.reset();

    const summary = acc.summary(0);
    expect(summary.matches).toEqual([]);
    expect(summary.totalPicked).toBe(0);
    expect(summary.alreadyUpgraded).toBe(0);
    expect(summary.unmatched).toBe(0);
  });
});
