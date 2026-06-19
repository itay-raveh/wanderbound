import type { AlbumChapter, DateRange, StepRead as Step } from "@/client";
import {
  mapRangesForSteps,
  stepsForChapter,
} from "@/components/album/albumChapters";
import {
  mapInsertionsByStep,
  rangeSectionKey,
} from "@/components/album/albumSections";
import type { ChapterVisit, GroupEntry, StepItem } from "./types";

type MapEntrySource = {
  rangeIdx: number;
  dateRange: DateRange;
};

type ChapterGroupsInput = {
  steps: Step[];
  stepItems: StepItem[];
  mapsRanges: DateRange[];
  chapters: AlbumChapter[];
  untitledLabel: (index: number) => string;
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

export function buildChapterGroups({
  steps,
  stepItems,
  mapsRanges,
  chapters,
  untitledLabel,
}: ChapterGroupsInput): ChapterVisit[] {
  return chapters.map((chapter, index) => {
    const chapterSteps = stepsForChapter(steps, chapter);
    const entries = entriesForSteps(chapterSteps, stepItems, mapsRanges);
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
      entryIndexByStepId,
    };
  });
}
