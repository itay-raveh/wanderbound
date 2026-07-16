import { uploadConfig } from "@/client";
import { useQuery } from "@pinia/colada";
import { queryKeys } from "./keys";

export function useUploadConfigQuery() {
  return useQuery({
    key: queryKeys.uploadConfig(),
    query: async () => (await uploadConfig()).data,
    staleTime: Infinity,
  });
}
