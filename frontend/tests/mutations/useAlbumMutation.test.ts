import { flushPromises } from "@vue/test-utils";
import { ref } from "vue";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import { BASE, defaultAlbum } from "../mocks/handlers";
import { deferred, withSetup } from "../helpers";
import { useAlbumQuery } from "@/queries/queries";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { useUndoStack } from "@/composables/useUndoStack";

describe("useAlbumMutation", () => {
  beforeEach(() => {
    useUndoStack().clear();
  });

  function mountAlbumMutation() {
    const aid = ref<string | null>(defaultAlbum.id);
    return withSetup(() => {
      const query = useAlbumQuery(aid);
      const mutation = useAlbumMutation(() => aid.value!);
      return { query, mutation };
    });
  }

  describe("optimistic update", () => {
    it("updates cache immediately before server responds", async () => {
      const result = mountAlbumMutation();

      await flushPromises();
      expect(result.query.data.value?.title).toBe("South America");

      const updateResponse = deferred<Response>();
      server.use(
        http.patch(`${BASE}/albums/:aid`, () => updateResponse.promise),
      );

      result.mutation.mutate({ title: "Updated Title" });
      await flushPromises();

      expect(result.query.data.value?.title).toBe("Updated Title");

      updateResponse.resolve(
        HttpResponse.json({ ...defaultAlbum, title: "Updated Title" }),
      );
      await flushPromises();
    });
  });

  describe("error rollback", () => {
    it("reverts cache to previous value on error", async () => {
      server.use(
        http.patch(`${BASE}/albums/:aid`, () =>
          HttpResponse.json({ detail: "Server error" }, { status: 500 }),
        ),
      );

      const result = mountAlbumMutation();

      await flushPromises();
      expect(result.query.data.value?.title).toBe("South America");

      result.mutation.mutate({ title: "Will Fail" });
      await flushPromises();

      expect(result.query.data.value?.title).toBe("South America");
    });
  });
});
