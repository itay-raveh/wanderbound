import type { AlbumChapter, DateRange } from "@/client";
import type { HeaderKey } from "@/components/album/albumSections";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { computed, ref, type Ref } from "vue";
import {
  adjustChapterBoundary,
  chapterCanSplit,
  deleteChapter as deleteChapterFromList,
  splitChapter,
} from "./chapterEditing";
import type { AlbumNavProps, ChapterVisit } from "./types";
import { useAlbumNavData } from "./useAlbumNavData";

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
  const albumMutation = useAlbumMutation(() => selectedAlbumId.value ?? "");
  const openChapterKey = ref<string | null>(null);
  const data = useAlbumNavData(props, selectedAlbumId);

  function updateChapters(chapters: AlbumChapter[]) {
    albumMutation.mutate({ chapters });
  }

  const chapterRows = computed(() =>
    data.chapterGroups.value.map((group, index, groups) => ({
      group,
      canDelete: groups.length > 1,
      canSplit: chapterCanSplit(group.chapter),
      mergeTarget: index === 0 ? ("next" as const) : ("previous" as const),
      startStepId: group.chapter.step_ids?.[0] ?? null,
      startOptions:
        index > 0
          ? data.boundaryOptions(groups[index - 1].chapter, group.chapter)
          : [],
    })),
  );

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
    const chapters = splitChapter(data.chaptersForNav.value, props.steps, chapterId);
    if (chapters === data.chaptersForNav.value) return;
    updateChapters(chapters);
    const sourceIndex = chapters.findIndex((chapter) => chapter.id === chapterId);
    const nextChapter = chapters[sourceIndex + 1];
    if (nextChapter) openChapterKey.value = nextChapter.id;
  }

  function onDeleteChapter(chapterId: string) {
    const chapters = deleteChapterFromList(data.chaptersForNav.value, chapterId);
    if (chapters === data.chaptersForNav.value) return;
    const deletedIndex = data.chaptersForNav.value.findIndex(
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
      data.chaptersForNav.value,
      leftChapterId,
      rightChapterId,
      firstRightStepId,
    );
    if (chapters !== data.chaptersForNav.value) updateChapters(chapters);
  }

  function onAdjustChapterBoundaryFromRow(index: number, firstRightStepId: number) {
    const leftChapterId = data.chapterGroups.value[index - 1]?.chapter.id;
    const rightChapterId = data.chapterGroups.value[index]?.chapter.id;
    if (!leftChapterId || !rightChapterId) return;
    onAdjustChapterBoundary(leftChapterId, rightChapterId, firstRightStepId);
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
    ...data,
    openChapterKey,
    chapterRows,
    onMapsRangesChange,
    toggleStep,
    toggleHeader,
    toggleChapter,
    onSplitChapter,
    onDeleteChapter,
    onAdjustChapterBoundaryFromRow,
    deleteMap,
    mapDateChange,
  };
}
