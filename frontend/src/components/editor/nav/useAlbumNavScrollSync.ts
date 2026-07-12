import { useActiveSection } from "@/composables/useActiveSection";
import { nextTick, watch, type Ref } from "vue";
import type { ChapterVisit, GroupEntry } from "./types";

type NavScrollSyncInput = {
  chapterGroups: Ref<ChapterVisit[]>;
  openChapterKey: Ref<string | null>;
  listRef: Ref<HTMLElement | undefined>;
};

export function useAlbumNavScrollSync({
  chapterGroups,
  openChapterKey,
  listRef,
}: NavScrollSyncInput) {
  const {
    activeStepId,
    activeSectionKey,
    setActive,
    scrollTo,
    scrollToSection,
    scrollBehavior,
    programmaticScrolling,
  } = useActiveSection();

  function scrollToMap(key: string) {
    if (scrollToSection(key)) {
      setActive(key);
      return;
    }
    const hikeKey = key.replace("-map-", "-hike-");
    if (hikeKey !== key && scrollToSection(hikeKey)) setActive(hikeKey);
  }

  function scrollToStep(id: number) {
    scrollTo(id);
    setActive(id);
  }

  function scrollToHeader(key: string) {
    if (scrollToSection(key)) setActive(key);
  }

  function scrollNavItemIntoView(selector: string) {
    void nextTick(() => {
      const el = listRef.value?.querySelector(selector);
      (el as HTMLElement | null)?.scrollIntoView({
        block: "center",
        behavior: scrollBehavior(),
      });
    });
  }

  function openGroupFor(predicate: (e: GroupEntry) => boolean) {
    for (const chapter of chapterGroups.value) {
      if (!chapter.entries.some(predicate)) continue;
      if (chapter.key !== openChapterKey.value)
        openChapterKey.value = chapter.key;
      return;
    }
  }

  watch(activeStepId, (id) => {
    if (id == null) return;
    openGroupFor((e) => e.type === "step" && e.item.id === id);
    if (programmaticScrolling.value) return;
    scrollNavItemIntoView(`[data-nav-step="${id}"]`);
  });

  watch(
    chapterGroups,
    (groups) => {
      if (!openChapterKey.value && groups[0]) {
        openChapterKey.value = groups[0].key;
      }
    },
    { immediate: true },
  );

  watch(activeSectionKey, (key) => {
    if (key == null) return;
    for (const chapter of chapterGroups.value) {
      if (chapter.headerItems.some((item) => item.key === key)) {
        if (chapter.key !== openChapterKey.value)
          openChapterKey.value = chapter.key;
        if (programmaticScrolling.value) return;
        scrollNavItemIntoView(`[data-nav-section="${key}"]`);
        return;
      }
      for (const entry of chapter.entries) {
        if (entry.type !== "map" || entry.key !== key) continue;
        if (chapter.key !== openChapterKey.value)
          openChapterKey.value = chapter.key;
        if (programmaticScrolling.value) return;
        scrollNavItemIntoView(`[data-nav-section="${entry.key}"]`);
        return;
      }
    }
  });

  return {
    activeStepId,
    activeSectionKey,
    scrollToStep,
    scrollToMap,
    scrollToHeader,
  };
}
