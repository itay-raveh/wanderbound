import type { AlbumChapter, DateRange, StepRead as Step } from "@/client";
import {
  mapRangeEntriesForSteps,
  stepsForChapter,
  type MapRangeEntry,
} from "@/components/album/albumChapters";
import {
  chapterHeaderSectionKey,
  type HeaderKey,
  mapInsertionsByStep,
  rangeSectionKey,
} from "@/components/album/albumSections";
import type {
  ChapterVisit,
  GroupEntry,
  StepItem,
} from "./types";

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
  source: MapRangeEntry,
  chapter: AlbumChapter,
  color: string,
): Extract<GroupEntry, { type: "map" }> {
  return {
    type: "map",
    rangeIdx: source.rangeIdx,
    dateRange: source.dateRange,
    key: rangeSectionKey("map", source.dateRange, chapter),
    color,
  };
}

function entriesForSteps(
  steps: Step[],
  stepItems: StepItem[],
  mapsRanges: DateRange[],
  chapter: AlbumChapter,
): GroupEntry[] {
  const byStepId = new Map(stepItems.map((item) => [item.id, item]));
  const insertions = mapInsertionsByStep(mapRangeEntriesForSteps(mapsRanges, steps));
  const entries: GroupEntry[] = [];
  for (const step of steps) {
    const item = byStepId.get(step.id);
    entries.push(
      ...(insertions
        .get(step.id)
        ?.map((entry) => toMapEntry(entry, chapter, item?.color ?? "")) ?? []),
    );
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
    const entries = entriesForSteps(chapterSteps, stepItems, mapsRanges, chapter);
    const entryIndexByStepId = new Map<number, number>();
    entries.forEach((entry, entryIndex) => {
      if (entry.type === "step") entryIndexByStepId.set(entry.item.id, entryIndex);
    });
    return {
      key: chapter.id,
      name: chapter.title || untitledLabel(index),
      chapter,
      chapterIndex: index,
      headerItems: headerKeys.map((headerKey) => ({
        key: chapterHeaderSectionKey(chapter.id, headerKey),
        headerKey,
        label: headerLabel(headerKey),
        icon: headerIcon(headerKey),
      })),
      stepIds: chapterSteps.map((step) => step.id),
      entries,
      entryIndexByStepId,
      dateRange: computeStepDateRange(
        entries.filter((entry) => entry.type === "step"),
        dateRangeLabel,
      ),
    };
  });
}
