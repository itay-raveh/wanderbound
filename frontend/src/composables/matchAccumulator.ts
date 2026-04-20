import type { MatchResult } from "@/client";

export interface MatchRound {
  matches: MatchResult[];
  totalPicked: number;
  alreadyUpgraded: number;
}

export interface MatchSummary {
  matches: MatchResult[];
  totalPicked: number;
  matched: number;
  alreadyUpgraded: number;
  unmatched: number;
  newThisRound: number;
}

export function createMatchAccumulator() {
  let matches: MatchResult[] = [];
  let totalPicked = 0;
  let alreadyUpgraded = 0;

  return {
    get matches() {
      return matches;
    },
    merge(round) {
      const byLocalName = new Map(matches.map((m) => [m.local_name, m]));
      const before = byLocalName.size;
      for (const m of round.matches) {
        const prev = byLocalName.get(m.local_name);
        if (!prev || m.distance < prev.distance) {
          byLocalName.set(m.local_name, m);
        }
      }
      matches = [...byLocalName.values()];
      totalPicked += round.totalPicked;
      alreadyUpgraded += round.alreadyUpgraded;
      return matches.length - before;
    },
    summary(newThisRound) {
      return {
        matches: [...matches],
        totalPicked,
        matched: matches.length,
        alreadyUpgraded,
        unmatched: Math.max(0, totalPicked - matches.length),
        newThisRound,
      };
    },
    reset() {
      matches = [];
      totalPicked = 0;
      alreadyUpgraded = 0;
    },
  };
}
