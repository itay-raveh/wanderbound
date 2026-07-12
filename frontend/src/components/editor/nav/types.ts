import type { AlbumChapter, AlbumMeta, DateRange, StepRead as Step } from "@/client";
import type { HeaderKey } from "@/components/album/albumSections";

export type AlbumNavProps = {
  album: AlbumMeta;
  steps: Step[];
  albumIds?: string[];
  hiddenSteps?: number[];
  hiddenHeaders?: HeaderKey[];
  colors?: Record<string, unknown>;
  mapsRanges?: DateRange[];
};

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

export interface ChapterStartOption {
  label: string;
  value: number;
  countryCode: string;
  countryLabel: string;
}

export type GroupEntry =
  | { type: "step"; item: StepItem }
  | {
      type: "map";
      rangeIdx: number;
      dateRange: DateRange;
      key: string;
      color: string;
    };

interface ChapterHeaderNavItem {
  key: string;
  headerKey: HeaderKey;
  icon: string;
  label: string;
}

export interface ChapterVisit {
  key: string;
  name: string;
  chapter: AlbumChapter;
  chapterIndex: number;
  headerItems: ChapterHeaderNavItem[];
  entries: GroupEntry[];
  entryIndexByStepId: Map<number, number>;
  stepIds: number[];
  dateRange: string;
}
