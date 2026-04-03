import { useQuery } from "@pinia/colada";
import { markRaw, type Ref } from "vue";
import { readAlbum, readMedia, readSteps, readSegments, readPrintBundle } from "@/client";
import { queryKeys, STALE_TIME } from "./keys";

type KeyFn = (aid: string | null) => readonly (string | null)[];

function createAlbumQuery<T extends object>(key: KeyFn, readFn: (opts: { path: { aid: string } }) => Promise<{ data: T }>) {
  return (aid: Ref<string | null>) =>
    useQuery({
      key: () => key(aid.value),
      query: async () => {
        if (!aid.value) throw new Error("No album selected");
        const { data } = await readFn({ path: { aid: aid.value } });
        return markRaw(data);
      },
      enabled: () => !!aid.value,
      staleTime: STALE_TIME,
    });
}

export const useAlbumQuery = createAlbumQuery(queryKeys.album, readAlbum);
export const useMediaQuery = createAlbumQuery(queryKeys.media, readMedia);
export const useStepsQuery = createAlbumQuery(queryKeys.steps, readSteps);
export const useSegmentsQuery = createAlbumQuery(queryKeys.segments, readSegments);
export const usePrintBundleQuery = createAlbumQuery(queryKeys.printBundle, readPrintBundle);
