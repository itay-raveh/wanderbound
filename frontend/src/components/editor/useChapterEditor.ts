import type {
  AlbumChapter,
  AlbumMedia,
  AlbumMeta,
  StepRead as Step,
} from "@/client";
import {
  applyStepRange,
  stepOptionsForChapter,
  unassignedSteps,
} from "@/components/album/albumChapters";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { isVideo } from "@/utils/media";
import { computed, reactive } from "vue";

type RangeDraft = { from: number | null; to: number | null };

type ChapterEditorProps = {
  album: AlbumMeta;
  steps: Step[];
  media: AlbumMedia[];
};

function optionalChapterText(
  value: string | number | null,
): string | null {
  return typeof value === "string" && value ? value : null;
}

export function useChapterEditor(props: ChapterEditorProps) {
  const albumMutation = useAlbumMutation(() => props.album.id);
  const rangeDrafts = reactive<Record<string, RangeDraft>>({});
  const chapters = computed(() => props.album.chapters ?? []);
  const unassigned = computed(() =>
    unassignedSteps(props.steps, chapters.value),
  );
  const coverOptions = computed(() =>
    props.media
      .filter((media) => !isVideo(media.name))
      .map((media) => ({ label: media.name, value: media.name })),
  );

  function chapterId(): string {
    const used = new Set(chapters.value.map((chapter) => chapter.id));
    for (let index = chapters.value.length + 1; ; index++) {
      const id = `chapter-${index}`;
      if (!used.has(id)) return id;
    }
  }

  function fallbackCover(): string {
    return (
      coverOptions.value[0]?.value ??
      props.album.front_cover_photo ??
      props.album.back_cover_photo
    );
  }

  function save(chapterList: AlbumChapter[]) {
    albumMutation.mutate({ chapters: chapterList });
  }

  function addChapter() {
    if (!unassigned.value.length) return;
    const cover = fallbackCover();
    save([
      ...chapters.value,
      {
        id: chapterId(),
        title: null,
        subtitle: null,
        step_ids: unassigned.value.map((step) => step.id),
        front_cover_photo: cover,
        back_cover_photo: cover,
      },
    ]);
  }

  function updateChapter(index: number, patch: Partial<AlbumChapter>) {
    if (patch.step_ids && patch.step_ids.length === 0) return;
    save(
      chapters.value.map((chapter, i) =>
        i === index ? { ...chapter, ...patch } : chapter,
      ),
    );
  }

  function deleteChapter(index: number) {
    save(chapters.value.filter((_, i) => i !== index));
  }

  function rangeDraft(chapter: AlbumChapter): RangeDraft {
    rangeDrafts[chapter.id] ??= { from: null, to: null };
    return rangeDrafts[chapter.id];
  }

  function stepOptionsFor(chapter: AlbumChapter) {
    return stepOptionsForChapter(props.steps, chapters.value, chapter);
  }

  function applyRange(index: number, chapter: AlbumChapter) {
    const draft = rangeDraft(chapter);
    if (draft.from == null || draft.to == null) return;
    const stepIds = applyStepRange(
      props.steps,
      chapters.value,
      chapter,
      draft.from,
      draft.to,
    );
    if (!stepIds.length) return;
    updateChapter(index, { step_ids: stepIds });
  }

  return {
    chapters,
    unassigned,
    coverOptions,
    optionalText: optionalChapterText,
    addChapter,
    updateChapter,
    deleteChapter,
    rangeDraft,
    stepOptionsFor,
    applyRange,
  };
}
