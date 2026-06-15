import type { AlbumChapter, DateRange, StepRead as Step } from "@/client";
import {
  mapRangesForSteps,
  stepsForChapter,
  unassignedSteps,
} from "@/components/album/albumChapters";
import {
  mapInsertionsByStep,
  rangeSectionKey,
} from "@/components/album/albumSections";
import type { ChapterVisit, CountryVisit, GroupEntry, StepItem } from "./types";

type MapEntrySource = {
  rangeIdx: number;
  dateRange: DateRange;
};

type ChapterGroupsInput = {
  steps: Step[];
  stepItems: StepItem[];
  mapsRanges: DateRange[];
  chapters: AlbumChapter[];
  unassignedLabel: string;
  untitledLabel: (index: number) => string;
};

type CountryVisitsInput = {
  stepItems: StepItem[];
  mapInsertions: Map<number, MapEntrySource[]>;
  countryName: (code: string, detail: string) => string;
  dateRangeLabel: (first: Date, last: Date) => string;
};

function toMapEntry(
  source: MapEntrySource,
): Extract<GroupEntry, { type: "map" }> {
  return {
    type: "map",
    rangeIdx: source.rangeIdx,
    dateRange: source.dateRange,
    key: rangeSectionKey("map", source.dateRange),
  };
}

export function entryKey(entry: GroupEntry): string {
  return entry.type === "step" ? `step-${entry.item.id}` : entry.key;
}

function mapEntriesForSteps(
  mapsRanges: DateRange[],
  chapterSteps: Step[],
): MapEntrySource[] {
  const ranges = mapRangesForSteps(mapsRanges, chapterSteps);
  return ranges
    .map((dateRange) => ({
      rangeIdx: mapsRanges.indexOf(dateRange),
      dateRange,
    }))
    .filter((entry) => entry.rangeIdx >= 0);
}

function entriesForSteps(
  steps: Step[],
  stepItems: StepItem[],
  mapsRanges: DateRange[],
): GroupEntry[] {
  const byStepId = new Map(stepItems.map((item) => [item.id, item]));
  const insertions = mapInsertionsByStep(
    steps,
    mapEntriesForSteps(mapsRanges, steps),
  );
  const entries: GroupEntry[] = [];
  for (const step of steps) {
    entries.push(...(insertions.get(step.id)?.map(toMapEntry) ?? []));
    const item = byStepId.get(step.id);
    if (item) entries.push({ type: "step", item });
  }
  return entries;
}

function computeGroupDateRange(
  entries: GroupEntry[],
  dateRangeLabel: (first: Date, last: Date) => string,
): string {
  const steps = entries.filter(
    (e): e is Extract<GroupEntry, { type: "step" }> => e.type === "step",
  );
  const first = steps[0]?.item.date;
  const last = steps.at(-1)?.item.date;
  if (!first || !last) return "";
  return dateRangeLabel(first, last);
}

export function buildCountryVisits({
  stepItems,
  mapInsertions,
  countryName,
  dateRangeLabel,
}: CountryVisitsInput): CountryVisit[] {
  const visits: CountryVisit[] = [];
  for (const item of stepItems) {
    const mapEntries = mapInsertions.get(item.id)?.map(toMapEntry) ?? [];
    const prev = visits.at(-1);
    if (prev && prev.code === item.country) {
      const stepEntryIndex = prev.entries.length + mapEntries.length;
      prev.entries.push(...mapEntries, { type: "step", item });
      prev.stepIds.push(item.id);
      prev.entryIndexByStepId.set(item.id, stepEntryIndex);
    } else {
      visits.push({
        key: `${item.country}-${visits.length}`,
        code: item.country,
        name: countryName(item.country, item.detail),
        color: item.color,
        entries: [...mapEntries, { type: "step", item }],
        stepIds: [item.id],
        entryIndexByStepId: new Map([[item.id, mapEntries.length]]),
        dateRange: "",
      });
    }
  }
  for (const visit of visits) {
    visit.dateRange = computeGroupDateRange(visit.entries, dateRangeLabel);
  }
  return visits;
}

export function buildChapterGroups({
  steps,
  stepItems,
  mapsRanges,
  chapters,
  unassignedLabel,
  untitledLabel,
}: ChapterGroupsInput): ChapterVisit[] {
  const groups = chapters.map((chapter, index) => {
    const chapterSteps = stepsForChapter(steps, chapter);
    return {
      key: chapter.id,
      name: chapter.title || untitledLabel(index),
      entries: entriesForSteps(chapterSteps, stepItems, mapsRanges),
      stepIds: chapterSteps.map((step) => step.id),
    };
  });

  const looseSteps = unassignedSteps(steps, chapters);
  if (looseSteps.length) {
    groups.push({
      key: "__unassigned__",
      name: unassignedLabel,
      entries: entriesForSteps(looseSteps, stepItems, mapsRanges),
      stepIds: looseSteps.map((step) => step.id),
    });
  }
  return groups;
}
