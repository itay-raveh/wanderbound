import type { AlbumChapter, DateRange } from "@/client";
import type { HeaderKey } from "@/components/album/albumSections";

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

export interface CountryVisit {
  key: string;
  code: string;
  name: string;
  color: string;
  entries: GroupEntry[];
  stepIds: number[];
  entryIndexByStepId: Map<number, number>;
  dateRange: string;
}

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
  countries: CountryVisit[];
  stepIds: number[];
}
