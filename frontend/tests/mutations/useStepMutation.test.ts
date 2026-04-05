import { flushPromises } from "@vue/test-utils";
import { ref } from "vue";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import { BASE, defaultAlbum, defaultSteps } from "../mocks/handlers";
import { withSetup } from "../helpers";
import { useStepsQuery } from "@/queries/queries";
import { useStepMutation } from "@/queries/useStepMutation";
import { useUndoStack } from "@/composables/useUndoStack";

const defaultStep = defaultSteps[0];

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
        const query = useStepsQuery(aid);
        const mutation = useStepMutation(() => aid.value!);
        return { query, mutation };
      });

      await flushPromises();
      expect(result.query.data.value?.[0]?.name).toBe("Amsterdam");

      server.use(
        http.patch(`${BASE}/albums/:aid/steps/:sid`, async () => {
          await new Promise((r) => setTimeout(r, 50));
          return HttpResponse.json({ ...defaultStep, name: "Rotterdam" });
        }),
      );

      result.mutation.mutate({ sid: 1, update: { name: "Rotterdam" } });
      await flushPromises();

      expect(result.query.data.value?.[0]?.name).toBe("Rotterdam");

      await new Promise((r) => setTimeout(r, 100));
      await flushPromises();
    });

    it("only updates the targeted step, leaving others unchanged", async () => {
      const step2 = {
        ...defaultStep,
        id: 2,
        name: "Berlin",
      };
      const updatedStep1 = { ...defaultStep, name: "Utrecht" };

      // First GET returns initial data; after mutation, GET returns updated data
      let mutated = false;
      server.use(
        http.get(`${BASE}/albums/:aid/steps`, () =>
          HttpResponse.json(mutated ? [updatedStep1, step2] : [defaultStep, step2]),
        ),
        http.patch(`${BASE}/albums/:aid/steps/:sid`, () => {
          mutated = true;
          return HttpResponse.json(updatedStep1);
        }),
      );

      const aid = ref<string | null>(defaultAlbum.id);

      const result = withSetup(() => {
        const query = useStepsQuery(aid);
        const mutation = useStepMutation(() => aid.value!);
        return { query, mutation };
      });

      await flushPromises();
      expect(result.query.data.value).toHaveLength(2);

      result.mutation.mutate({ sid: 1, update: { name: "Utrecht" } });
      await flushPromises();

      expect(result.query.data.value?.[0]?.name).toBe("Utrecht");
      expect(result.query.data.value?.[1]?.name).toBe("Berlin");
    });

});

  // ---------------------------------------------------------------------------
  // Undo stack integration
  // ---------------------------------------------------------------------------

  describe("undo stack", () => {
    it("stores step-specific before/after snapshots", async () => {
      const aid = ref<string | null>(defaultAlbum.id);
      const undoStack = useUndoStack();
      const stepMutator = vi.fn();
      undoStack.registerMutators(stepMutator, vi.fn());

      const result = withSetup(() => {
        const query = useStepsQuery(aid);
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
        const query = useStepsQuery(aid);
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

});
