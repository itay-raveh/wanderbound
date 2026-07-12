import type {
  AlbumChapter,
  AlbumMeta,
  DateRange,
  StepRead as Step,
} from "@/client";
import { HEADER_KEYS, type HeaderKey } from "@/components/album/albumSections";
import { getCountryColor } from "@/components/album/colors";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { useUserQuery } from "@/queries/useUserQuery";
import { parseLocalDate, SHORT_DATE } from "@/utils/date";
import { mediaThumbUrl } from "@/utils/media";
import {
  symOutlinedBarChart,
  symOutlinedMap,
  symOutlinedMenuBook,
} from "@quasar/extras/material-symbols-outlined";
import { computed, ref, type Ref } from "vue";
import { useI18n } from "vue-i18n";
import {
  adjustChapterBoundary,
  deleteChapter as deleteChapterFromList,
  splitChapter,
} from "./chapterEditing";
import { buildChapterGroups } from "./useAlbumNavGroups";
import type { ChapterVisit, StepItem } from "./types";

export type AlbumNavProps = {
  album: AlbumMeta;
  steps: Step[];
  albumIds?: string[];
  hiddenSteps?: number[];
  hiddenHeaders?: HeaderKey[];
  colors?: Record<string, unknown>;
  mapsRanges?: DateRange[];
};

type StartOption = {
  label: string;
  value: number;
  countryCode: string;
  countryLabel: string;
};

const HEADER_ICONS: Record<HeaderKey, string> = {
  "cover-front": symOutlinedMenuBook,
  "cover-back": symOutlinedMenuBook,
  overview: symOutlinedBarChart,
  "full-map": symOutlinedMap,
};

const HEADER_LABELS: Record<HeaderKey, string> = {
  "cover-front": "nav.cover",
  "cover-back": "album.backCover",
  overview: "inspector.overview",
  "full-map": "album.tripRouteMap",
};

const toTitleCase = (str: string) =>
  str
    .replace(/([a-z])-/g, "$1 ")
    .replace(/_\d+$/, "")
    .replace(
      /\w\S*/g,
      (text) => text.charAt(0).toUpperCase() + text.substring(1).toLowerCase(),
    );

function toggleInList<T>(list: readonly T[], item: T): T[] {
  const copy = [...list];
  const idx = copy.indexOf(item);
  if (idx >= 0) copy.splice(idx, 1);
  else copy.push(item);
  return copy;
}

export function useAlbumNavModel(
  props: AlbumNavProps,
  selectedAlbumId: Ref<string | null | undefined>,
) {
  const { t } = useI18n();
  const { formatDateRange, countryName } = useUserQuery();
  const albumMutation = useAlbumMutation(() => selectedAlbumId.value ?? "");
  const openChapterKey = ref<string | null>(null);

  const albumOptions = computed(() =>
    (props.albumIds ?? []).map((value) => ({ label: toTitleCase(value), value })),
  );
  const hiddenSet = computed(() => new Set(props.hiddenSteps ?? []));
  const hiddenHeaderSet = computed(() => new Set(props.hiddenHeaders ?? []));
  const albumColors = computed(
    () => (props.colors ?? {}) as Record<string, string>,
  );
  const stepItems = computed<StepItem[]>(() =>
    props.steps.map((s) => ({
      id: s.id,
      name: s.name,
      country: s.location.country_code,
      countryLabel: countryName(s.location.country_code, s.location.detail),
      color: getCountryColor(
        props.colors as Record<string, string>,
        s.location.country_code,
      ),
      date: parseLocalDate(s.datetime),
      thumb:
        s.cover && selectedAlbumId.value
          ? mediaThumbUrl(s.cover, selectedAlbumId.value)
          : null,
      detail: s.location.detail,
    })),
  );
  const chaptersForNav = computed<AlbumChapter[]>(() => props.album.chapters ?? []);
  const chapterGroups = computed(() =>
    buildChapterGroups({
      steps: props.steps,
      stepItems: stepItems.value,
      mapsRanges: props.mapsRanges ?? [],
      chapters: chaptersForNav.value,
      headerKeys: HEADER_KEYS,
      headerLabel: (key) => t(HEADER_LABELS[key]),
      headerIcon: (key) => HEADER_ICONS[key],
      untitledLabel: (index) => t("chapters.untitled", { number: index + 1 }),
      dateRangeLabel: (first, last) => formatDateRange(first, last, SHORT_DATE),
    }),
  );

  function formatMapRange(dr: DateRange): string {
    return formatDateRange(
      parseLocalDate(dr[0]),
      parseLocalDate(dr[1]),
      SHORT_DATE,
    );
  }

  function stepLabel(stepId: number): string {
    const step = props.steps.find((candidate) => candidate.id === stepId);
    return step?.name || step?.location.name || String(stepId);
  }

  function boundaryOptions(
    left: AlbumChapter,
    right: AlbumChapter,
  ): StartOption[] {
    const combined = [...(left.step_ids ?? []), ...(right.step_ids ?? [])];
    return combined.slice(1).map((stepId) => {
      const step = props.steps.find((candidate) => candidate.id === stepId);
      const countryCode = step?.location.country_code ?? "";
      return {
        label: stepLabel(stepId),
        value: stepId,
        countryCode,
        countryLabel: step
          ? countryName(countryCode, step.location.detail)
          : String(stepId),
      };
    });
  }

  function updateChapters(chapters: AlbumChapter[]) {
    albumMutation.mutate({ chapters });
  }

  function onMapsRangesChange(ranges: DateRange[]) {
    albumMutation.mutate({ maps_ranges: ranges });
  }

  function toggleStep(stepId: number) {
    albumMutation.mutate({
      hidden_steps: toggleInList(props.hiddenSteps ?? [], stepId),
    });
  }

  function toggleHeader(key: HeaderKey) {
    albumMutation.mutate({
      hidden_headers: toggleInList(props.hiddenHeaders ?? [], key),
    });
  }

  function toggleChapter(group: ChapterVisit) {
    if (openChapterKey.value === group.key) {
      openChapterKey.value = null;
      return;
    }
    openChapterKey.value = group.key;
  }

  function onSplitChapter(chapterId: string) {
    const chapters = splitChapter(chaptersForNav.value, props.steps, chapterId);
    if (chapters === chaptersForNav.value) return;
    updateChapters(chapters);
    const sourceIndex = chapters.findIndex((chapter) => chapter.id === chapterId);
    const nextChapter = chapters[sourceIndex + 1];
    if (nextChapter) openChapterKey.value = nextChapter.id;
  }

  function onDeleteChapter(chapterId: string) {
    const chapters = deleteChapterFromList(chaptersForNav.value, chapterId);
    if (chapters === chaptersForNav.value) return;
    const deletedIndex = chaptersForNav.value.findIndex(
      (chapter) => chapter.id === chapterId,
    );
    updateChapters(chapters);
    if (openChapterKey.value === chapterId) {
      openChapterKey.value =
        chapters[Math.min(deletedIndex, chapters.length - 1)]?.id ?? null;
    }
  }

  function onAdjustChapterBoundary(
    leftChapterId: string,
    rightChapterId: string,
    firstRightStepId: number,
  ) {
    const chapters = adjustChapterBoundary(
      chaptersForNav.value,
      leftChapterId,
      rightChapterId,
      firstRightStepId,
    );
    if (chapters !== chaptersForNav.value) updateChapters(chapters);
  }

  function deleteMap(rangeIdx: number) {
    const ranges = [...(props.mapsRanges ?? [])];
    ranges.splice(rangeIdx, 1);
    albumMutation.mutate({ maps_ranges: ranges });
  }

  function mapDateChange(rangeIdx: number, range: DateRange) {
    const ranges = [...(props.mapsRanges ?? [])] as DateRange[];
    const existing = ranges[rangeIdx];
    if (existing) {
      ranges[rangeIdx] = [existing[0], range[1]];
      albumMutation.mutate({ maps_ranges: ranges });
    }
  }

  return {
    t,
    albumOptions,
    hiddenSet,
    hiddenHeaderSet,
    albumColors,
    chapterGroups,
    openChapterKey,
    formatMapRange,
    boundaryOptions,
    onMapsRangesChange,
    toggleStep,
    toggleHeader,
    toggleChapter,
    onSplitChapter,
    onDeleteChapter,
    onAdjustChapterBoundary,
    deleteMap,
    mapDateChange,
  };
}
