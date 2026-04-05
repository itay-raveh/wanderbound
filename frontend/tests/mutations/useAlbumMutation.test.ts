import { flushPromises } from "@vue/test-utils";
import { ref } from "vue";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import { BASE, defaultAlbum } from "../mocks/handlers";
import { withSetup } from "../helpers";
import { useAlbumQuery } from "@/queries/queries";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { useUndoStack } from "@/composables/useUndoStack";

describe("useAlbumMutation", () => {
  beforeEach(() => {
    useUndoStack().clear();
  });

  // ---------------------------------------------------------------------------
  // Optimistic update
  // ---------------------------------------------------------------------------

  describe("optimistic update", () => {
    it("updates cache immediately before server responds", async () => {
      const aid = ref<string | null>(defaultAlbum.id);

      const result = withSetup(() => {
        const query = useAlbumQuery(aid);
        const mutation = useAlbumMutation(() => aid.value!);
        return { query, mutation };
      });

      // Wait for initial query to load
      await flushPromises();
      expect(result.query.data.value?.title).toBe("South America");

      server.use(
        http.patch(`${BASE}/albums/:aid`, async () => {
          await new Promise((r) => setTimeout(r, 50));
          return HttpResponse.json({ ...defaultAlbum, title: "Updated Title" });
        }),
      );

      result.mutation.mutate({ title: "Updated Title" });
      await flushPromises();

      expect(result.query.data.value?.title).toBe("Updated Title");

      // Let the delayed response settle before MSW resets handlers
      await new Promise((r) => setTimeout(r, 100));
      await flushPromises();
    });

});

  // ---------------------------------------------------------------------------
  // Error rollback
  // ---------------------------------------------------------------------------

  describe("error rollback", () => {
    it("reverts cache to previous value on error", async () => {
      server.use(
        http.patch(`${BASE}/albums/:aid`, () =>
          HttpResponse.json({ detail: "Server error" }, { status: 500 }),
        ),
      );

      const aid = ref<string | null>(defaultAlbum.id);

      const result = withSetup(() => {
        const query = useAlbumQuery(aid);
        const mutation = useAlbumMutation(() => aid.value!);
        return { query, mutation };
      });

      await flushPromises();
      expect(result.query.data.value?.title).toBe("South America");

      result.mutation.mutate({ title: "Will Fail" });
      await flushPromises();

      expect(result.query.data.value?.title).toBe("South America");
    });
  });

});
