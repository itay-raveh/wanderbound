import type { AlbumChapter, DateRange } from "@/client";
import { HEADER_KEYS, type HeaderKey } from "@/components/album/albumSections";
import { getCountryColor } from "@/components/album/colors";
import { useUserQuery } from "@/queries/useUserQuery";
import { parseLocalDate, SHORT_DATE } from "@/utils/date";
import { mediaThumbUrl } from "@/utils/media";
import {
  symOutlinedBarChart,
  symOutlinedMap,
  symOutlinedMenuBook,
} from "@quasar/extras/material-symbols-outlined";
import { computed, type Ref } from "vue";
import { useI18n } from "vue-i18n";
import { chapterBoundaryOptions } from "./chapterBoundaryOptions";
import type { AlbumNavProps } from "./types";
import { buildChapterGroups } from "./useAlbumNavGroups";

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

export function useAlbumNavData(
  props: AlbumNavProps,
  selectedAlbumId: Ref<string | null | undefined>,
) {
  const { t } = useI18n();
  const { formatDateRange, countryName } = useUserQuery();

  const albumOptions = computed(() =>
    (props.albumIds ?? []).map((value) => ({ label: toTitleCase(value), value })),
  );
  const hiddenSet = computed(() => new Set(props.hiddenSteps ?? []));
  const hiddenHeaderSet = computed(() => new Set(props.hiddenHeaders ?? []));
  const albumColors = computed(
    () => (props.colors ?? {}) as Record<string, string>,
  );
  const chaptersForNav = computed<AlbumChapter[]>(() => props.album.chapters ?? []);
  const stepItems = computed(() =>
    props.steps.map((step) => ({
      id: step.id,
      name: step.name,
      country: step.location.country_code,
      countryLabel: countryName(step.location.country_code, step.location.detail),
      color: getCountryColor(albumColors.value, step.location.country_code),
      date: parseLocalDate(step.datetime),
      thumb:
        step.cover && selectedAlbumId.value
          ? mediaThumbUrl(step.cover, selectedAlbumId.value)
          : null,
      detail: step.location.detail,
    })),
  );
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

  function formatMapRange(dateRange: DateRange): string {
    return formatDateRange(
      parseLocalDate(dateRange[0]),
      parseLocalDate(dateRange[1]),
      SHORT_DATE,
    );
  }

  function boundaryOptions(left: AlbumChapter, right: AlbumChapter) {
    return chapterBoundaryOptions({
      left,
      right,
      steps: props.steps,
      countryName,
    });
  }

  return {
    t,
    albumOptions,
    hiddenSet,
    hiddenHeaderSet,
    albumColors,
    chaptersForNav,
    chapterGroups,
    formatMapRange,
    boundaryOptions,
  };
}
