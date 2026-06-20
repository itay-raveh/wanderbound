import type { AlbumChapter, DateRange, StepRead as Step } from "@/client";
import {
  mapRangesForSteps,
  stepsForChapter,
} from "@/components/album/albumChapters";
import {
  chapterHeaderSectionKey,
  type HeaderKey,
  mapInsertionsByStep,
  rangeSectionKey,
} from "@/components/album/albumSections";
import type {
  ChapterCountryRun,
  ChapterVisit,
  GroupEntry,
  StepItem,
} from "./types";

type MapEntrySource = {
  rangeIdx: number;
  dateRange: DateRange;
};

type ChapterGroupsInput = {
  steps: Step[];
  stepItems: StepItem[];
  mapsRanges: DateRange[];
  chapters: AlbumChapter[];
  headerKeys: readonly HeaderKey[];
  headerLabel: (key: HeaderKey) => string;
  headerIcon: (key: HeaderKey) => string;
  untitledLabel: (index: number) => string;
  dateRangeLabel: (first: Date, last: Date) => string;
};

function toMapEntry(
  source: MapEntrySource,
  chapter: AlbumChapter,
): Extract<GroupEntry, { type: "map" }> {
  return {
    type: "map",
    rangeIdx: source.rangeIdx,
    dateRange: source.dateRange,
    key: rangeSectionKey("map", source.dateRange, chapter),
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
  chapter: AlbumChapter,
): GroupEntry[] {
  const byStepId = new Map(stepItems.map((item) => [item.id, item]));
  const insertions = mapInsertionsByStep(
    steps,
    mapEntriesForSteps(mapsRanges, steps),
  );
  const entries: GroupEntry[] = [];
  for (const step of steps) {
    entries.push(
      ...(insertions.get(step.id)?.map((entry) => toMapEntry(entry, chapter)) ??
        []),
    );
    const item = byStepId.get(step.id);
    if (item) entries.push({ type: "step", item });
  }
  return entries;
}

function computeStepDateRange(
  steps: Extract<GroupEntry, { type: "step" }>[],
  dateRangeLabel: (first: Date, last: Date) => string,
): string {
  const first = steps[0]?.item.date;
  const last = steps.at(-1)?.item.date;
  if (!first || !last) return "";
  return dateRangeLabel(first, last);
}

function computeCountryRuns(
  entries: GroupEntry[],
  dateRangeLabel: (first: Date, last: Date) => string,
): ChapterCountryRun[] {
  const runs: Array<
    Omit<ChapterCountryRun, "dateRange"> & {
      stepEntries: Extract<GroupEntry, { type: "step" }>[];
    }
  > = [];
  entries.forEach((entry, entryIndex) => {
    if (entry.type !== "step") return;
    const prev = runs.at(-1);
    if (prev && prev.code === entry.item.country) {
      prev.stepIds.push(entry.item.id);
      prev.stepEntries.push(entry);
    } else {
      runs.push({
        code: entry.item.country,
        name: entry.item.countryLabel,
        color: entry.item.color,
        stepIds: [entry.item.id],
        firstEntryIndex: entryIndex,
        stepEntries: [entry],
      });
    }
  });
  return runs.map(({ stepEntries, ...run }) => ({
    ...run,
    dateRange: computeStepDateRange(stepEntries, dateRangeLabel),
  }));
}

export function buildChapterGroups({
  steps,
  stepItems,
  mapsRanges,
  chapters,
  headerKeys,
  headerLabel,
  headerIcon,
  untitledLabel,
  dateRangeLabel,
}: ChapterGroupsInput): ChapterVisit[] {
  return chapters.map((chapter, index) => {
    const chapterSteps = stepsForChapter(steps, chapter);
    const entries: GroupEntry[] = [
      ...headerKeys.map((headerKey) => ({
        type: "header" as const,
        key: chapterHeaderSectionKey(chapter.id, headerKey),
        headerKey,
        label: headerLabel(headerKey),
        icon: headerIcon(headerKey),
      })),
      ...entriesForSteps(chapterSteps, stepItems, mapsRanges, chapter),
    ];
    const entryIndexByStepId = new Map<number, number>();
    entries.forEach((entry, entryIndex) => {
      if (entry.type === "step") {
        entryIndexByStepId.set(entry.item.id, entryIndex);
      }
    });
    return {
      key: chapter.id,
      name: chapter.title || untitledLabel(index),
      chapter,
      chapterIndex: index,
      entries,
      stepIds: chapterSteps.map((step) => step.id),
      countryRuns: computeCountryRuns(entries, dateRangeLabel),
      entryIndexByStepId,
    };
  });
}
