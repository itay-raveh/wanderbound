import { flushPromises } from "@vue/test-utils";
import { ref } from "vue";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import { BASE, defaultAlbum, defaultAlbumData } from "../mocks/handlers";
import { withSetup } from "../helpers";
import { useAlbumDataQuery } from "@/queries/useAlbumDataQuery";
import { useStepMutation } from "@/queries/useStepMutation";
import { useUndoStack } from "@/composables/useUndoStack";

describe("useStepMutation", () => {
  beforeEach(() => {
    useUndoStack().clear();
  });

  // ---------------------------------------------------------------------------
  // Optimistic update
  // ---------------------------------------------------------------------------

  describe("optimistic update", () => {
    it("updates the matching step in cache immediately", async () => {
      const aid = ref<string | null>(defaultAlbum.id);

      const result = withSetup(() => {
        const query = useAlbumDataQuery(aid);
        const mutation = useStepMutation(() => aid.value!);
        return { query, mutation };
      });

      await flushPromises();
      expect(result.query.data.value?.steps[0]?.name).toBe("Amsterdam");

      server.use(
        http.patch(`${BASE}/albums/:aid/steps/:sid`, async () => {
          await new Promise((r) => setTimeout(r, 50));
          return HttpResponse.json({ ...defaultAlbumData.steps[0], name: "Rotterdam" });
        }),
      );

      result.mutation.mutate({ sid: 1, update: { name: "Rotterdam" } });
      await flushPromises();

      expect(result.query.data.value?.steps[0]?.name).toBe("Rotterdam");

      await new Promise((r) => setTimeout(r, 100));
      await flushPromises();
    });

    it("only updates the targeted step, leaving others unchanged", async () => {
      const step2 = {
        ...defaultAlbumData.steps[0],
        id: 2,
        name: "Berlin",
      };
      const updatedStep1 = { ...defaultAlbumData.steps[0], name: "Utrecht" };
      const updatedData = {
        steps: [updatedStep1, step2],
        segments: [],
      };
      const initialData = {
        steps: [defaultAlbumData.steps[0], step2],
        segments: [],
      };

      // First GET returns initial data; after mutation, GET returns updated data
      let mutated = false;
      server.use(
        http.get(`${BASE}/albums/:aid/data`, () =>
          HttpResponse.json(mutated ? updatedData : initialData),
        ),
        http.patch(`${BASE}/albums/:aid/steps/:sid`, () => {
          mutated = true;
          return HttpResponse.json(updatedStep1);
        }),
      );

      const aid = ref<string | null>(defaultAlbum.id);

      const result = withSetup(() => {
        const query = useAlbumDataQuery(aid);
        const mutation = useStepMutation(() => aid.value!);
        return { query, mutation };
      });

      await flushPromises();
      expect(result.query.data.value?.steps).toHaveLength(2);

      result.mutation.mutate({ sid: 1, update: { name: "Utrecht" } });
      await flushPromises();

      expect(result.query.data.value?.steps[0]?.name).toBe("Utrecht");
      expect(result.query.data.value?.steps[1]?.name).toBe("Berlin");
    });

    it("merges only the updated fields on the step", async () => {
      const updatedStep = {
        ...defaultAlbumData.steps[0],
        name: "New Name",
      };
      const updatedData = {
        steps: [updatedStep],
        segments: [],
      };

      let mutated = false;
      server.use(
        http.get(`${BASE}/albums/:aid/data`, () =>
          HttpResponse.json(mutated ? updatedData : defaultAlbumData),
        ),
        http.patch(`${BASE}/albums/:aid/steps/:sid`, () => {
          mutated = true;
          return HttpResponse.json(updatedStep);
        }),
      );

      const aid = ref<string | null>(defaultAlbum.id);

      const result = withSetup(() => {
        const query = useAlbumDataQuery(aid);
        const mutation = useStepMutation(() => aid.value!);
        return { query, mutation };
      });

      await flushPromises();
      const originalDescription =
        result.query.data.value?.steps[0]?.description;

      result.mutation.mutate({ sid: 1, update: { name: "New Name" } });
      await flushPromises();

      expect(result.query.data.value?.steps[0]?.name).toBe("New Name");
      expect(result.query.data.value?.steps[0]?.description).toBe(
        originalDescription,
      );
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
        const query = useAlbumDataQuery(aid);
        const mutation = useStepMutation(() => aid.value!);
        return { query, mutation };
      });

      await flushPromises();
      expect(undoStack.canUndo.value).toBe(false);

      result.mutation.mutate({ sid: 1, update: { name: "Changed" } });
      await flushPromises();

      expect(undoStack.canUndo.value).toBe(true);
    });

    it("stores step-specific before/after snapshots", async () => {
      const aid = ref<string | null>(defaultAlbum.id);
      const undoStack = useUndoStack();
      const stepMutator = vi.fn();
      undoStack.registerMutators(stepMutator, vi.fn());

      const result = withSetup(() => {
        const query = useAlbumDataQuery(aid);
        const mutation = useStepMutation(() => aid.value!);
        return { query, mutation };
      });

      await flushPromises();

      result.mutation.mutate({ sid: 1, update: { name: "New Name" } });
      await flushPromises();

      undoStack.undo();
      expect(stepMutator).toHaveBeenCalledWith(1, { name: "Amsterdam" });
    });

    it("does not push to undo stack if step is not found", async () => {
      const aid = ref<string | null>(defaultAlbum.id);
      const undoStack = useUndoStack();

      const result = withSetup(() => {
        const query = useAlbumDataQuery(aid);
        const mutation = useStepMutation(() => aid.value!);
        return { query, mutation };
      });

      await flushPromises();

      // Mutate a non-existent step id
      result.mutation.mutate({ sid: 999, update: { name: "Ghost" } });
      await flushPromises();

      expect(undoStack.canUndo.value).toBe(false);
    });
  });

  // ---------------------------------------------------------------------------
  // Error rollback
  // ---------------------------------------------------------------------------

  describe("error rollback", () => {
    it("reverts cache to previous data on error", async () => {
      server.use(
        http.patch(`${BASE}/albums/:aid/steps/:sid`, () =>
          HttpResponse.json({ detail: "Server error" }, { status: 500 }),
        ),
      );

      const aid = ref<string | null>(defaultAlbum.id);

      const result = withSetup(() => {
        const query = useAlbumDataQuery(aid);
        const mutation = useStepMutation(() => aid.value!);
        return { query, mutation };
      });

      await flushPromises();
      expect(result.query.data.value?.steps[0]?.name).toBe("Amsterdam");

      result.mutation.mutate({ sid: 1, update: { name: "Will Fail" } });
      await flushPromises();

      expect(result.query.data.value?.steps[0]?.name).toBe("Amsterdam");
    });
  });

  // ---------------------------------------------------------------------------
  // API call
  // ---------------------------------------------------------------------------

  describe("API call", () => {
    it("sends the correct aid, sid, and body to the API", async () => {
      let capturedAid: string | undefined;
      let capturedSid: string | undefined;
      let capturedBody: Record<string, unknown> | undefined;

      server.use(
        http.patch(
          `${BASE}/albums/:aid/steps/:sid`,
          async ({ params, request }) => {
            capturedAid = params.aid as string;
            capturedSid = params.sid as string;
            capturedBody = (await request.json()) as Record<string, unknown>;
            return HttpResponse.json({
              ...defaultAlbumData.steps[0],
              name: "Sent Name",
            });
          },
        ),
      );

      const aid = ref<string | null>(defaultAlbum.id);

      const result = withSetup(() => {
        const query = useAlbumDataQuery(aid);
        const mutation = useStepMutation(() => aid.value!);
        return { query, mutation };
      });

      await flushPromises();

      result.mutation.mutate({ sid: 1, update: { name: "Sent Name" } });
      await flushPromises();

      expect(capturedAid).toBe(defaultAlbum.id);
      expect(capturedSid).toBe("1");
      expect(capturedBody).toEqual({ name: "Sent Name" });
    });
  });
});
