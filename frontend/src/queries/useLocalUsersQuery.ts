import { listLocalUsers } from "@/client";
import { useQuery } from "@pinia/colada";
import type { Ref } from "vue";
import { queryKeys } from "./keys";

export function useLocalUsersQuery(open: Ref<boolean>) {
  return useQuery({
    key: queryKeys.localUsers(),
    query: async () => (await listLocalUsers()).data,
    enabled: () => open.value,
  });
}
