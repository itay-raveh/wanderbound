import type { AlbumChapter } from "@/client";
import type { PdfExportTarget } from "@/composables/usePdfExportStream";
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";

export function usePdfChapterSelection(chapters: () => AlbumChapter[]) {
  const { t } = useI18n();
  const selectedChapterIds = ref<string[]>([]);
  const chapterOptions = computed(chapters);
  const selectedCount = computed(() => selectedChapterIds.value.length);
  const allChaptersSelected = computed({
    get: () =>
      chapterOptions.value.length > 0 &&
      selectedChapterIds.value.length === chapterOptions.value.length,
    set: (checked: boolean) => {
      selectedChapterIds.value = checked
        ? chapterOptions.value.map((chapter) => chapter.id)
        : [];
    },
  });
  const someChaptersSelected = computed(
    () =>
      selectedChapterIds.value.length > 0 &&
      selectedChapterIds.value.length < chapterOptions.value.length,
  );
  const chapterOptionItems = computed(() =>
    chapterOptions.value.map((chapter, index) => ({
      label: chapter.title || t("chapters.untitled", { number: index + 1 }),
      value: chapter.id,
    })),
  );

  watch(
    chapterOptions,
    (nextChapters) => {
      const valid = new Set(nextChapters.map((chapter) => chapter.id));
      const kept = selectedChapterIds.value.filter((id) => valid.has(id));
      selectedChapterIds.value =
        kept.length > 0 ? kept : nextChapters.map((chapter) => chapter.id);
    },
    { immediate: true },
  );

  function selectedExportTarget(): PdfExportTarget | null {
    const ids = selectedChapterIds.value;
    if (ids.length === 0) return null;
    return ids.length === 1
      ? { type: "chapter", id: ids[0] }
      : { type: "chapters", ids };
  }

  return {
    chapterOptions,
    chapterOptionItems,
    selectedChapterIds,
    selectedCount,
    allChaptersSelected,
    someChaptersSelected,
    selectedExportTarget,
  };
}
