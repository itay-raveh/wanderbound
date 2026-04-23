import { useQuery } from "@pinia/colada";
import { authState } from "@/client";
import { queryKeys } from "./keys";

export function useAuthStateQuery() {
  return useQuery({
    key: queryKeys.authState(),
    query: async () => (await authState()).data,
    staleTime: Infinity,
  });
}
