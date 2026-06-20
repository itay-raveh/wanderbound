import type { AlbumChapter, DateRange } from "@/client";

export interface StepItem {
  id: number;
  name: string;
  country: string;
  countryLabel: string;
  color: string;
  date: Date;
  thumb: string | null;
  detail: string;
}

export type GroupEntry =
  | { type: "step"; item: StepItem }
  | { type: "map"; rangeIdx: number; dateRange: DateRange; key: string };

export interface ChapterCountryRun {
  code: string;
  name: string;
  color: string;
  stepIds: number[];
  firstEntryIndex: number;
  dateRange: string;
}

export interface ChapterVisit {
  key: string;
  name: string;
  chapter: AlbumChapter;
  chapterIndex: number;
  entries: GroupEntry[];
  stepIds: number[];
  countryRuns: ChapterCountryRun[];
  entryIndexByStepId: Map<number, number>;
}
