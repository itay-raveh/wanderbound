import { useMutation, useQueryCache } from "@pinia/colada";
import { updateUser } from "@/client";
import type { User, UserUpdate } from "@/client";
import { Notify } from "quasar";
import { queryKeys } from "./keys";

export function useUserMutation() {
  const cache = useQueryCache();

  return useMutation({
    mutation: async (body: UserUpdate) => {
      const { data } = await updateUser({ body });
      return data;
    },
    onMutate: (body) => {
      const key = queryKeys.user();
      const prev = cache.getQueryData<User>(key);
      if (prev) {
        cache.setQueryData(key, { ...prev, ...body });
      }
      return prev;
    },
    onError: (_error, _vars, prev) => {
      if (prev) {
        cache.setQueryData(queryKeys.user(), prev);
      }
      Notify.create({ type: "negative", message: "Failed to update preference" });
    },
    onSettled: () => {
      void cache.invalidateQueries({ key: queryKeys.user(), exact: true });
    },
  });
}
