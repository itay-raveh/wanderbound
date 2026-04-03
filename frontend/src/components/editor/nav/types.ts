import type { DateRange } from "@/client";

export interface StepItem {
  id: number;
  name: string;
  country: string;
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
  dateRange: string;
}
