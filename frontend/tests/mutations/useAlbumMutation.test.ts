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

    it("merges only the updated fields", async () => {
      const updatedAlbum = { ...defaultAlbum, subtitle: "New Subtitle" };

      server.use(
        http.patch(`${BASE}/albums/:aid`, () =>
          HttpResponse.json(updatedAlbum),
        ),
        http.get(`${BASE}/albums/:aid`, () =>
          HttpResponse.json(updatedAlbum),
        ),
      );

      const aid = ref<string | null>(defaultAlbum.id);

      const result = withSetup(() => {
        const query = useAlbumQuery(aid);
        const mutation = useAlbumMutation(() => aid.value!);
        return { query, mutation };
      });

      await flushPromises();

      result.mutation.mutate({ subtitle: "New Subtitle" });
      await flushPromises();

      expect(result.query.data.value?.title).toBe("South America");
      expect(result.query.data.value?.subtitle).toBe("New Subtitle");
    });
  });

  // ---------------------------------------------------------------------------
  // Undo stack integration
  // ---------------------------------------------------------------------------

  describe("undo stack", () => {
    it("pushes an entry to the undo stack on mutate", async () => {
      const aid = ref<string | null>(defaultAlbum.id);
      const undoStack = useUndoStack();

      const result = withSetup(() => {
        const query = useAlbumQuery(aid);
        const mutation = useAlbumMutation(() => aid.value!);
        return { query, mutation };
      });

      await flushPromises();
      expect(undoStack.canUndo.value).toBe(false);

      result.mutation.mutate({ title: "Changed" });
      await flushPromises();

      expect(undoStack.canUndo.value).toBe(true);
    });

    it("stores before/after snapshots of changed keys only", async () => {
      const aid = ref<string | null>(defaultAlbum.id);
      const undoStack = useUndoStack();
      const albumMutator = vi.fn();
      undoStack.registerMutators(vi.fn(), albumMutator);

      const result = withSetup(() => {
        const query = useAlbumQuery(aid);
        const mutation = useAlbumMutation(() => aid.value!);
        return { query, mutation };
      });

      await flushPromises();

      result.mutation.mutate({ title: "New Title" });
      await flushPromises();

      undoStack.undo();
      expect(albumMutator).toHaveBeenCalledWith({ title: "South America" });
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

  // ---------------------------------------------------------------------------
  // API call
  // ---------------------------------------------------------------------------

  describe("API call", () => {
    it("sends the correct aid and body to the API", async () => {
      let capturedAid: string | undefined;
      let capturedBody: Record<string, unknown> | undefined;

      server.use(
        http.patch(`${BASE}/albums/:aid`, async ({ params, request }) => {
          capturedAid = params.aid as string;
          capturedBody = (await request.json()) as Record<string, unknown>;
          return HttpResponse.json({
            ...defaultAlbum,
            title: "Sent Title",
          });
        }),
      );

      const aid = ref<string | null>(defaultAlbum.id);

      const result = withSetup(() => {
        const query = useAlbumQuery(aid);
        const mutation = useAlbumMutation(() => aid.value!);
        return { query, mutation };
      });

      await flushPromises();

      result.mutation.mutate({ title: "Sent Title" });
      await flushPromises();

      expect(capturedAid).toBe(defaultAlbum.id);
      expect(capturedBody).toEqual({ title: "Sent Title" });
    });
  });
});
